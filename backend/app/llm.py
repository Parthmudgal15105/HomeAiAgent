from abc import ABC, abstractmethod
import json
import math
import time
from copy import deepcopy
from itertools import product
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from .config import Settings
from .safety import redact
from .schemas import Decision, IncidentSpec


SYSTEM_PROMPT = '''ROLE: Infrastructure incident orchestrator.
TASK: Choose exactly one next action from ALLOWED_TOOLS.

SYMPTOM:
{symptom}

EVIDENCE:
{only relevant observations}

ALLOWED_TOOLS:
{only currently valid tools}

RULES:
- Use evidence only.
- Never invent results.
- Never repeat completed checks.
- Prefer the cheapest diagnostic that reduces uncertainty.
- For queue or job-processing symptoms while the site remains reachable, inspect the worker logs before resource statistics.
- Choose one tool only.
- If enough evidence exists, STOP.
- If no tool can investigate further, ESCALATE.
- Output valid schema only.

OUTPUT:
{"action":"tool|STOP|ESCALATE","reason":"short reason","args":{}}

The supplied JSON schema is authoritative: encode the selected action in that schema, use only its allowed tool names and arguments, and return one JSON object with no prose.'''

CLASSIFICATION_PROMPT = '''Classify this infrastructure incident. Return JSON only.
category: http_service|container|process|systemd_service|network|disk|database|unknown.
target: named affected host, container, process, service, or empty.
symptom: short restatement. confidence: 0 to 1.
Do not select tools or propose actions.'''


def remaining_parameters(tool: dict, observations: list[dict]) -> dict | None:
    """Narrow finite diagnostic target choices after each snapshot, never widen access.

    Optional sampling knobs (log lines/count) do not make the same target a new
    diagnostic. Unknown schema shapes retain the executor's duplicate guard.
    The full static registry stays in the prompt to preserve its inference cache.
    """
    schema = deepcopy(tool['parameters'])
    last_write = max((index for index, item in enumerate(observations) if item.get('phase') == 'REMEDIATION'), default=-1)
    prior = [o.get('tool_arguments', o.get('arguments', {})) for o in observations[last_write + 1:] if o.get('tool_name') == tool['name']]
    if not prior or tool.get('risk_level') != 'READ_ONLY':
        return schema
    required = schema.get('required', [])
    if not required:
        return None
    properties = schema.get('properties', {})
    choices = [properties.get(key, {}).get('enum') for key in required]
    if not all(choices):
        return schema
    count = 1
    for values in choices:
        count *= len(values)
    if count > 256:
        return schema
    branches = []
    for values in product(*choices):
        target = dict(zip(required, values))
        if any(all(old.get(key) == value for key, value in target.items()) for old in prior):
            continue
        branch = deepcopy(schema)
        for key, value in target.items():
            branch['properties'][key] = {**branch['properties'][key], 'enum': [value]}
        branches.append(branch)
    return {'anyOf': branches} if branches else None


def parse_decision(content: str) -> Decision:
    """Extract one complete JSON object; never execute code or salvage partial objects."""
    if not isinstance(content, str) or len(content) > 64000:
        raise ValueError('Model response exceeds limit or is not text')
    value = content.strip()
    if value.startswith('```') and value.endswith('```'):
        value = '\n'.join(value.splitlines()[1:-1]).strip()
    # A complete outer object may be surrounded by explanatory text. Starting at
    # the first brace and decoding exactly once deliberately rejects truncated
    # outer objects, multiple objects and arrays of competing decisions.
    start = value.find('{')
    if start < 0 or '[' in value[:start]:
        raise ValueError('Model did not return one JSON decision object')
    decoded, end = json.JSONDecoder().raw_decode(value[start:])
    suffix = value[start + end:]
    if any(mark in suffix for mark in ('{', '}', '[', ']')):
        raise ValueError('Ambiguous or multiple model decision objects')
    return Decision.model_validate(decoded)


def parse_incident_spec(content: str) -> IncidentSpec:
    if not isinstance(content, str) or len(content) > 4000:
        raise ValueError('Incident classification response is invalid')
    value = content.strip()
    if value.startswith('```') and value.endswith('```'):
        value = '\n'.join(value.splitlines()[1:-1]).strip()
    return IncidentSpec.model_validate(json.loads(value))


def ollama_action_schema(context: dict) -> dict:
    """Use the smallest possible local-model contract for one bounded action.

    The agent still validates arguments against the live registry before calling a
    tool.  Keeping that large, dynamic schema out of Qwen's constrained decoder
    avoids asking a small local model to emit an entire incident report at every
    diagnostic step.
    """
    from .context import compact_schema
    reason = {'type': 'string', 'minLength': 3, 'maxLength': 180}
    variants = []
    for tool in context.get('tools', []):
        if tool.get('risk_level') != 'READ_ONLY':
            continue
        parameters = remaining_parameters(tool, context.get('observations', []))
        if parameters is None:
            continue
        variants.append({
            'type': 'object',
            'properties': {'action': {'type': 'string', 'const': tool['name']}, 'reason': reason,
                           'args': compact_schema(parameters)},
            'required': ['action', 'reason', 'args'], 'additionalProperties': False,
        })
    for action in ('STOP', 'ESCALATE'):
        variants.append({
            'type': 'object',
            'properties': {'action': {'type': 'string', 'const': action}, 'reason': reason,
                           'args': {'type': 'object', 'maxProperties': 0}},
            'required': ['action', 'reason', 'args'], 'additionalProperties': False,
        })
    return {'anyOf': variants}


def parse_ollama_action(content: str, context: dict) -> Decision:
    """Convert the minimal local contract to the internal, policy-checked type."""
    if not isinstance(content, str) or len(content) > 64000:
        raise ValueError('Model response exceeds limit or is not text')
    value = content.strip()
    if value.startswith('```') and value.endswith('```'):
        value = '\n'.join(value.splitlines()[1:-1]).strip()
    parsed = json.loads(value)
    if set(parsed) != {'action', 'reason', 'args'} or not isinstance(parsed['reason'], str) or not isinstance(parsed['args'], dict):
        raise ValueError('Model did not return the minimal action schema')
    action, reason, args = parsed['action'], parsed['reason'], parsed['args']
    allowed = {tool['name'] for tool in context.get('tools', []) if tool.get('risk_level') == 'READ_ONLY'}
    if action in allowed:
        return Decision(decision_type='TOOL_CALL', tool=action, arguments=args, reason=reason)
    if action == 'ESCALATE':
        return Decision(decision_type='NEED_USER_INPUT', reason=reason, summary=reason, capability_status='KNOWN_TOOL')
    if action == 'STOP':
        evidence = [item['id'] for item in context.get('observations', [])]
        if evidence:
            return Decision(decision_type='DIAGNOSIS', reason=reason, root_cause=reason, summary=reason,
                            evidence_observation_ids=[evidence[-1]])
        return Decision(decision_type='STOP', reason=reason, summary=reason)
    raise ValueError('Model selected an action outside the current allowlist')


def model_prompt_context(context: dict) -> dict:
    """Remove prompt duplicates while retaining model-relevant incident topology.

    The response-format schema already carries every permitted argument enum and
    constraint. Repeating those schemas inside the user message makes a small
    CPU model spend most of its context window rereading identical JSON.
    """
    value = deepcopy(context)
    if 'tools' in context:
        value['tools'] = [
            {key: (tool[key][:72] if key == 'description' and isinstance(tool.get(key), str) else tool[key])
             for key in ('name', 'description', 'risk_level') if key in tool}
            for tool in context.get('tools', [])
        ]
    topology = context.get('topology')
    services = topology.get('services', {}) if isinstance(topology, dict) else {}
    service = context.get('incident', {}).get('service')
    selected: set[str] = set()

    def include(name: str):
        if name in selected or name not in services:
            return
        selected.add(name)
        for dependency in services[name].get('depends_on', []):
            include(dependency)

    if service:
        include(service)
    if not selected:
        selected = set(services)
    if isinstance(topology, dict):
        value['topology'] = {
            'services': {
                name: {
                    key: (profile[key][:180] if key == 'description' and isinstance(profile.get(key), str) else profile[key])
                    for key in ('description', 'depends_on') if key in profile
                }
                for name, profile in services.items() if name in selected
            }
        }
    return value


def ollama_prompt_tokens(content: str, schema: dict) -> int:
    """Conservative configuration guard; it never changes Ollama's limits."""
    payload = len(SYSTEM_PROMPT) + len(content) + len(json.dumps(schema, separators=(',', ':'), ensure_ascii=False))
    # JSON syntax is token-dense, so a four-character estimate is intentionally
    # only a preflight guard rather than a claim of tokenizer precision.
    return math.ceil(payload / 4)


def validate_ollama_prompt_budget(settings: Settings, content: str, schema: dict) -> None:
    estimated = ollama_prompt_tokens(content, schema)
    required = estimated + settings.ollama_num_predict
    if required > settings.ollama_num_ctx:
        raise RuntimeError(
            f'Ollama prompt budget exceeds OLLAMA_NUM_CTX ({required} estimated tokens required; '
            f'configured {settings.ollama_num_ctx}). Reduce context/output tokens or measure a larger context window.'
        )


def decision_schema(context: dict) -> dict:
    """Constrain each tool to its exact live registry schema; executor revalidates."""
    from .context import compact_schema
    original = compact_schema(Decision.model_json_schema())
    definitions = original.get('$defs', {})
    evidence_ids = [item['id'] for item in context.get('observations', [])]
    ids = {'type': 'array', 'maxItems': 8, 'items': {'type': 'string', 'enum': evidence_ids}} if evidence_ids else {'type': 'array', 'maxItems': 0, 'items': {'type': 'string'}}
    hypothesis = definitions['HypothesisUpdate']
    hypothesis['properties']['description']['maxLength'] = 180
    hypothesis['properties']['supporting_observation_ids'] = deepcopy(ids)
    hypothesis['properties']['contradicting_observation_ids'] = deepcopy(ids)
    hypothesis['required'] = ['description', 'confidence', 'status', 'supporting_observation_ids', 'contradicting_observation_ids']
    hypotheses = {'type': 'array', 'maxItems': 2, 'items': {'$ref': '#/$defs/HypothesisUpdate'}}
    reason = {'type': 'string', 'maxLength': 180}
    variants = []
    writes = []
    for tool in context.get('tools', []):
        parameters = remaining_parameters(tool, context.get('observations', []))
        if parameters is None:
            continue
        props = {'tool': {'type': 'string', 'const': tool['name']}, 'arguments': compact_schema(parameters)}
        if tool.get('risk_level') == 'READ_ONLY':
            variants.append({'type': 'object', 'properties': {'reason': reason, 'decision_type': {'type': 'string', 'const': 'TOOL_CALL'}, **props, 'hypothesis_updates': hypotheses}, 'required': ['reason', 'decision_type', 'tool', 'arguments', 'hypothesis_updates'], 'additionalProperties': False})
        elif tool.get('risk_level') == 'LOW_RISK_WRITE':
            if context.get('autonomous_actions_enabled') and tool['name'].startswith('stop_'):
                continue
            props['reason'] = reason
            writes.append({'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False})
            variants.append({'type': 'object', 'properties': {'decision_type': {'type': 'string', 'const': 'EXECUTE_ACTION' if context.get('autonomous_actions_enabled') else 'REQUEST_APPROVAL'}, **props}, 'required': ['decision_type', *props], 'additionalProperties': False})
    if evidence_ids:
        props = {key: deepcopy(original['properties'][key]) for key in ('root_cause', 'confidence', 'summary', 'eliminated_causes', 'verification_plan', 'prevention')}
        props['root_cause'] = {'type': 'string', 'minLength': 3, 'maxLength': 400}
        props['summary'] = {'type': 'string', 'maxLength': 700}
        for key in ('eliminated_causes', 'verification_plan', 'prevention'):
            props[key] = {'type': 'array', 'maxItems': 3, 'items': {'type': 'string', 'maxLength': 180}}
        props.update({'decision_type': {'type': 'string', 'const': 'DIAGNOSIS'}, 'evidence_observation_ids': {**ids, 'minItems': 1}, 'hypothesis_updates': hypotheses, 'remediation': {'type': 'array', 'maxItems': 2 if writes else 0, 'items': {'anyOf': writes} if writes else {'type': 'object'}}})
        variants.append({'type': 'object', 'properties': {'reason': reason, 'decision_type': props.pop('decision_type'), **props}, 'required': ['reason', 'decision_type', 'root_cause', 'confidence', 'summary', 'evidence_observation_ids', 'hypothesis_updates', 'remediation', 'verification_plan', 'eliminated_causes', 'prevention'], 'additionalProperties': False})
    for kind in ('NEED_USER_INPUT', 'STOP'):
        properties = {
            'reason': reason,
            'decision_type': {'type': 'string', 'const': kind},
            'summary': {'type': 'string', 'maxLength': 700},
        }
        if kind == 'NEED_USER_INPUT':
            properties.update({
                'capability_status': {'type': 'string', 'enum': ['KNOWN_TOOL', 'MISSING_TOOL']},
                'capability_gap': {'type': 'string', 'maxLength': 160, 'pattern': '^[a-z0-9][a-z0-9_.-]*$'},
                'missing_capability': {'type': 'string', 'maxLength': 500},
                'recommended_next_check': {'type': 'string', 'maxLength': 500},
            })
        variants.append({'type': 'object', 'properties': properties,
                         'required': ['reason', 'decision_type'], 'additionalProperties': False})
    return {'anyOf': variants, '$defs': definitions}


def gemini_schema(schema: dict, evidence_ids: list[str] | None = None) -> dict:
    """Translate constraints unsupported by Gemini's JSON Schema subset.

    Gemini rejects some large unions containing repeated dynamic UUID enums.
    Evidence ownership remains enforced by Agent before persistence or action.
    """
    evidence = set(evidence_ids or [])

    def convert(value):
        if isinstance(value, list):
            return [convert(item) for item in value]
        if not isinstance(value, dict):
            return deepcopy(value)
        result = {}
        for key, item in value.items():
            if key == 'const':
                result['enum'] = [deepcopy(item)]
            elif key == 'enum' and evidence and item and set(item) <= evidence:
                continue
            elif key not in {'minLength', 'maxLength', 'pattern'}:
                result[key] = convert(item)
        return result

    return convert(schema)


class LLMProvider(ABC):
    @abstractmethod
    async def decide_next_action(self, context: dict) -> Decision:
        raise NotImplementedError

    async def generate_report(self, context: dict) -> Decision:
        return await self.decide_next_action({**context, 'report_requested': True})

    async def classify_incident(self, incident: dict) -> IncidentSpec:
        # Providers without the compact local classifier retain the bounded
        # reasoning path rather than guessing a route.
        return IncidentSpec(category='unknown', target='', symptom=incident.get('description', ''), confidence=0)


class OllamaLLMProvider(LLMProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.metrics = {
            'requests': 0, 'invalid_json': 0, 'retries': 0, 'failed_decisions': 0,
            'first_token_ms': [], 'model_load_time_ms': [], 'prompt_eval_time_ms': [],
            'generation_time_ms': [], 'total_model_time_ms': [], 'tokens_per_second': [],
            # Compatibility keys for existing reports. New code should use the
            # explicit names above rather than infer timing meaning from these.
            'latencies_ms': [], 'load_ms': [], 'prompt_eval_ms': [],
        }

    def record_timing(self, final: dict, total_ms: float, first_token: float | None) -> None:
        load_ms = round(final.get('load_duration', 0) / 1e6, 1) if final else None
        prompt_eval_ms = round(final.get('prompt_eval_duration', 0) / 1e6, 1) if final else None
        generation_ms = round(final.get('eval_duration', 0) / 1e6, 1) if final else None
        duration_ns = final.get('eval_duration', 0) if final else 0
        eval_count = final.get('eval_count', 0) if final else 0
        tokens_per_second = round(eval_count / (duration_ns / 1e9), 2) if duration_ns else None
        self.metrics['first_token_ms'].append(first_token)
        self.metrics['model_load_time_ms'].append(load_ms)
        self.metrics['prompt_eval_time_ms'].append(prompt_eval_ms)
        self.metrics['generation_time_ms'].append(generation_ms)
        self.metrics['total_model_time_ms'].append(total_ms)
        self.metrics['tokens_per_second'].append(tokens_per_second)
        self.metrics['latencies_ms'].append(total_ms)
        self.metrics['load_ms'].append(load_ms)
        self.metrics['prompt_eval_ms'].append(prompt_eval_ms)

    async def classify_incident(self, incident: dict) -> IncidentSpec:
        content = json.dumps(redact({key: incident.get(key, '') for key in ('title', 'description', 'service')}), separators=(',', ':'), ensure_ascii=False)
        schema = IncidentSpec.model_json_schema()
        validate_ollama_prompt_budget(self.settings, content, schema)
        messages = [{'role': 'system', 'content': CLASSIFICATION_PROMPT}, {'role': 'user', 'content': content}]
        async with httpx.AsyncClient(timeout=self.settings.agent_llm_timeout_seconds, trust_env=False) as client:
            for attempt in range(2):
                started, raw, first_token, final = time.monotonic(), '', None, {}
                self.metrics['requests'] += 1
                try:
                    async with client.stream('POST', self.settings.ollama_base_url.rstrip('/') + '/api/chat', json={
                        'model': self.settings.ollama_model, 'messages': messages, 'stream': True,
                        'format': schema, 'think': False, 'keep_alive': self.settings.ollama_keep_alive,
                        'options': {'temperature': 0, 'seed': 42, 'num_ctx': self.settings.ollama_num_ctx,
                                    'num_predict': min(96, self.settings.ollama_num_predict), 'num_thread': self.settings.ollama_num_thread},
                    }) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            chunk = json.loads(line)
                            if chunk.get('error'):
                                raise RuntimeError('Local model service error: ' + str(redact(chunk['error'], 500)))
                            piece = chunk.get('message', {}).get('content', '')
                            if piece and first_token is None:
                                first_token = round((time.monotonic() - started) * 1000, 1)
                            raw += piece
                            if chunk.get('done'):
                                final = chunk
                    if not final:
                        raise ValueError('Local model response stream ended before completion')
                except Exception:
                    self.metrics['failed_decisions'] += 1
                    raise
                finally:
                    self.record_timing(final, round((time.monotonic() - started) * 1000, 1), first_token)
                try:
                    return parse_incident_spec(raw)
                except (ValueError, ValidationError) as exc:
                    self.metrics['invalid_json'] += 1
                    if attempt:
                        self.metrics['failed_decisions'] += 1
                        raise ValueError('Local model returned invalid incident classification twice') from exc
                    self.metrics['retries'] += 1
                    messages.extend([{'role': 'assistant', 'content': str(redact(raw, 1000))}, {'role': 'user', 'content': 'Return only valid classification JSON.'}])
        raise RuntimeError('No incident classification returned')

    async def decide_next_action(self, context: dict) -> Decision:
        # Context is bounded structurally by the orchestrator, never by slicing JSON.
        prompt_context = model_prompt_context(context)
        content = json.dumps(redact(prompt_context), separators=(',', ':'), ensure_ascii=False)
        if len(content) > self.settings.agent_context_chars:
            raise ValueError('Structured model context exceeds configured character budget')
        schema = ollama_action_schema(context)
        validate_ollama_prompt_budget(self.settings, content, schema)
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': content}]
        async with httpx.AsyncClient(timeout=self.settings.agent_llm_timeout_seconds, trust_env=False) as client:
            for attempt in range(2):
                started = time.monotonic()
                self.metrics['requests'] += 1
                raw = ''
                first_token = None
                final = {}
                try:
                    async with client.stream('POST', self.settings.ollama_base_url.rstrip('/') + '/api/chat', json={
                        'model': self.settings.ollama_model,
                        'messages': messages,
                        'stream': True,
                        'format': schema,
                        'think': False,
                        'keep_alive': self.settings.ollama_keep_alive,
                        'options': {'temperature': 0, 'seed': 42, 'num_ctx': self.settings.ollama_num_ctx, 'num_predict': self.settings.ollama_num_predict, 'num_thread': self.settings.ollama_num_thread},
                    }) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            chunk = json.loads(line)
                            if chunk.get('error'):
                                raise RuntimeError('Local model service error: ' + str(redact(chunk['error'], 500)))
                            piece = chunk.get('message', {}).get('content', '')
                            if piece and first_token is None:
                                first_token = round((time.monotonic() - started) * 1000, 1)
                            raw += piece
                            if len(raw) > 64000:
                                raise ValueError('Model response exceeds limit')
                            if chunk.get('done'):
                                final = chunk
                    if not final:
                        raise ValueError('Local model response stream ended before completion')
                except Exception:
                    self.metrics['failed_decisions'] += 1
                    raise
                finally:
                    self.record_timing(final, round((time.monotonic() - started) * 1000, 1), first_token)
                try:
                    return parse_ollama_action(raw, context)
                except (ValueError, ValidationError) as exc:
                    self.metrics['invalid_json'] += 1
                    if attempt:
                        self.metrics['failed_decisions'] += 1
                        raise ValueError('Local model returned invalid structured decisions twice') from exc
                    self.metrics['retries'] += 1
                    messages.extend([{'role': 'assistant', 'content': str(redact(raw, 8000))}, {'role': 'user', 'content': 'Repair your last output into one valid schema-conforming JSON object. Validation error: ' + str(redact(str(exc), 1000))}])
        raise RuntimeError('No model decision returned')


class GeminiLLMProvider(LLMProvider):
    """Google Gemini Interactions API provider with fail-closed local validation."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.metrics = {
            'requests': 0, 'invalid_json': 0, 'retries': 0,
            'failed_decisions': 0, 'latencies_ms': [],
            'input_tokens': [], 'output_tokens': [], 'thought_tokens': [],
        }

    def endpoint(self) -> str:
        base = self.settings.gemini_base_url.rstrip('/')
        parsed = urlsplit(base)
        if (parsed.scheme != 'https' or parsed.hostname != 'generativelanguage.googleapis.com'
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('GEMINI_BASE_URL must be an HTTPS generativelanguage.googleapis.com endpoint')
        return base + '/interactions'

    def model_endpoint(self) -> str:
        base = self.endpoint().rsplit('/interactions', 1)[0]
        return base + '/models/' + quote(self.settings.gemini_model, safe='')

    @staticmethod
    def output_text(payload: dict) -> str:
        if payload.get('status') != 'completed':
            raise ValueError('Gemini interaction did not complete')
        parts = [
            item.get('text', '')
            for step in payload.get('steps', []) if step.get('type') == 'model_output'
            for item in step.get('content', []) if item.get('type') == 'text'
        ]
        content = ''.join(parts)
        if not content:
            raise ValueError('Gemini interaction returned no text output')
        return content

    async def decide_next_action(self, context: dict) -> Decision:
        content = json.dumps(redact(model_prompt_context(context)), separators=(',', ':'), ensure_ascii=False)
        if len(content) > self.settings.agent_context_chars:
            raise ValueError('Structured model context exceeds configured character budget')
        credential = self.settings.gemini_api_key.get_secret_value()
        if not credential:
            raise ValueError('GEMINI_API_KEY is required when LLM_PROVIDER=gemini')
        prompt = content
        evidence_ids = [item['id'] for item in context.get('observations', [])]
        schema = gemini_schema(decision_schema(context), evidence_ids)
        async with httpx.AsyncClient(timeout=self.settings.agent_llm_timeout_seconds, trust_env=False) as client:
            for attempt in range(2):
                started = time.monotonic()
                self.metrics['requests'] += 1
                try:
                    response = await client.post(
                        self.endpoint(),
                        headers={'x-goog-api-key': credential},
                        json={
                            'model': self.settings.gemini_model,
                            'input': prompt,
                            'system_instruction': SYSTEM_PROMPT,
                            'response_format': {
                                'type': 'text',
                                'mime_type': 'application/json',
                                'schema': schema,
                            },
                            'generation_config': {
                                'thinking_level': self.settings.gemini_thinking_level,
                                'max_output_tokens': self.settings.gemini_max_output_tokens,
                            },
                            'store': False,
                        },
                    )
                    if response.is_error:
                        detail = str(redact(response.text, 2000))
                        raise RuntimeError(f'Gemini API request failed with HTTP {response.status_code}: {detail}')
                    payload = response.json()
                    raw = self.output_text(payload)
                    usage = payload.get('usage', {})
                    self.metrics['input_tokens'].append(usage.get('total_input_tokens'))
                    self.metrics['output_tokens'].append(usage.get('total_output_tokens'))
                    self.metrics['thought_tokens'].append(usage.get('total_thought_tokens'))
                except Exception:
                    self.metrics['failed_decisions'] += 1
                    raise
                finally:
                    self.metrics['latencies_ms'].append(round((time.monotonic() - started) * 1000, 1))
                try:
                    return parse_decision(raw)
                except (ValueError, ValidationError) as exc:
                    self.metrics['invalid_json'] += 1
                    if attempt:
                        self.metrics['failed_decisions'] += 1
                        raise ValueError('Gemini returned invalid structured decisions twice') from exc
                    self.metrics['retries'] += 1
                    prompt = (
                        content + '\n\nYour previous response was invalid. Return one corrected JSON object only. '
                        'Validation error: ' + str(redact(str(exc), 1000)) +
                        '\nPrevious response: ' + str(redact(raw, 8000))
                    )
        raise RuntimeError('No model decision returned')


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == 'gemini':
        return GeminiLLMProvider(settings)
    return OllamaLLMProvider(settings)
