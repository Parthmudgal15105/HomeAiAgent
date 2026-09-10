"""Budget model context without weakening the executor's schemas or losing citations."""
from copy import deepcopy
import json
import re


def size(value) -> int:
    return len(json.dumps(value, separators=(',', ':'), ensure_ascii=False))


def clipped(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:max(0, limit - 14)] + '…[abbreviated]'


def compact_schema(schema):
    """Remove JSON Schema annotations, never property names, enums, consts or constraints."""
    if not isinstance(schema, dict):
        return deepcopy(schema)
    annotations = {'title', 'description', 'default', 'examples', '$comment', 'deprecated', 'readOnly', 'writeOnly'}
    named = {'properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'}
    children = {'items', 'additionalItems', 'additionalProperties', 'unevaluatedItems', 'unevaluatedProperties', 'contains', 'propertyNames', 'not', 'if', 'then', 'else'}
    branches = {'allOf', 'anyOf', 'oneOf', 'prefixItems'}
    result = {}
    for key, value in schema.items():
        if key in annotations:
            continue
        if key in named:
            result[key] = {name: compact_schema(child) for name, child in value.items()}
        elif key in children:
            result[key] = compact_schema(value)
        elif key in branches:
            result[key] = [compact_schema(child) for child in value]
        else:
            # enum/const objects can themselves contain keys named title/default.
            result[key] = deepcopy(value)
    return result


IMPORTANT = {'error', 'state', 'status', 'running', 'health', 'healthy', 'resolved', 'reachable', 'open', 'status_code', 'severity', 'used_percent', 'percent', 'restart_count', 'oom_killed', 'exit_code', 'rfkill', 'soft_blocked', 'hard_blocked', 'name', 'container', 'address', 'addresses', 'interfaces', 'containers', 'missing_configured_containers'}
ERROR = re.compile(r'error|fail|unavailable|refused|denied|timeout|timed out|fatal|rf.?kill|blocked|no space', re.I)


def interesting(item) -> bool:
    if not isinstance(item, dict):
        return bool(ERROR.search(str(item)))
    return (item.get('healthy') is False or item.get('open') is False or item.get('reachable') is False
            or item.get('health') in ('unhealthy', 'starting') or item.get('state') in ('exited', 'restarting', 'dead', 'DOWN', 'inactive')
            or bool(item.get('soft_blocked')) or bool(item.get('hard_blocked')))


def sampled(value, text_limit: int, item_limit: int, depth: int = 0):
    if isinstance(value, str):
        return clipped(value, text_limit)
    if isinstance(value, list):
        if len(value) <= item_limit:
            chosen = value
        else:
            failures = [item for item in value if interesting(item)]
            chosen = (failures[:1] if item_limit == 1 else failures[:1] + failures[-(item_limit - 1):]) if len(failures) > item_limit else (failures + [item for item in value if not interesting(item)])[:item_limit]
        return [sampled(item, text_limit, item_limit, depth + 1) for item in chosen]
    if isinstance(value, dict):
        if depth > 4:
            return {'_context_note': 'Nested details omitted; original observation is persisted.'}
        result = {}
        keys = sorted(value, key=lambda key: key not in IMPORTANT)
        for key in keys[:20]:
            item = value[key]
            if key in ('lines', 'entries', 'output'):
                lines = item.splitlines() if isinstance(item, str) else item
                if isinstance(lines, list):
                    lines = [entry.get('message', '') if isinstance(entry, dict) else str(entry) for entry in lines]
                    errors = [line for line in lines if ERROR.search(line)]
                    excerpts = ([errors[0]] + errors[-1:]) if errors else lines[-2:]
                    result[key] = [clipped(line, text_limit) for line in dict.fromkeys(excerpts)][:min(2, item_limit)]
                    result['_context_total_log_entries'] = len(lines)
                    continue
            result[key] = sampled(item, text_limit, item_limit, depth + 1)
            if isinstance(item, list) and len(item) > item_limit:
                result['_context_total_' + key] = len(item)
        return result
    return value


def compact_result(result: dict, budget: int, summary: str) -> dict:
    if size(result) <= budget:
        return result
    for text_limit, item_limit in ((220, 6), (140, 4), (90, 2), (60, 1)):
        candidate = sampled(result, text_limit, item_limit)
        candidate['_context_abbreviated'] = True
        if size(candidate) <= budget:
            return candidate
    # The deterministic interpretation preserves the observed finding even when a
    # very wide result cannot fit. Full raw/normalized data remain in PostgreSQL.
    return {'_context_summary': clipped(summary, max(0, budget - 40))}


def compact_context(context: dict, budget: int) -> dict:
    if size(context) <= budget:
        return context
    value = deepcopy(context)
    value['context_compacted'] = 'Some bulky results are summarized; all observation IDs are retained. Full evidence remains persisted.'
    for tool in value['tools']:
        tool['parameters'] = compact_schema(tool['parameters'])
    topology = value.get('topology', {})
    # Retain the whole dependency graph. Terse descriptions avoid removing a
    # potentially relevant reverse dependency based only on the initial symptom.
    for service in topology.get('services', {}).values():
        if isinstance(service.get('description'), str):
            service['description'] = clipped(service['description'], 220)
    value['incident']['description'] = clipped(value['incident'].get('description', ''), 1200)
    for hypothesis in value['hypotheses']:
        hypothesis['description'] = clipped(hypothesis['description'], 250)
    for key in ('retrieved_incidents', 'retrieved_runbooks'):
        value[key] = sampled(value.get(key, [])[:2], 600, 3)
    originals = []
    for observation in value['observations']:
        originals.append(observation['result'])
        observation['result'] = {}
        observation['interpretation'] = clipped(observation.get('interpretation', ''), 180)
    if size(value) > budget - 128 * len(originals):
        # Current observations take precedence over historical guidance.
        value['retrieved_incidents'] = []
        value['retrieved_runbooks'] = []
    available = budget - size(value) - 32
    if available < 100 * len(originals):
        raise ValueError('Context budget cannot retain tool constraints and current observation identities. Increase AGENT_CONTEXT_CHARS or begin a new incident.')
    # Allocate by result size so small boolean/HTTP results remain intact and log
    # observations receive the remaining budget. Never slice serialized JSON.
    weights = [min(1800, max(100, size(result))) for result in originals]
    total = sum(weights) or 1
    for observation, original, weight in zip(value['observations'], originals, weights):
        allocation = max(100, int(available * weight / total))
        observation['result'] = compact_result(original, allocation, observation['interpretation'])
    if size(value) > budget:
        # A minimum allocation can overrun a tight weighted budget; use equal
        # budgets as the conservative final pass, retaining every citation.
        each = available // max(1, len(originals))
        for observation, original in zip(value['observations'], originals):
            observation['result'] = compact_result(original, each, observation['interpretation'])
    if size(value) > budget:
        raise ValueError('Unable to compact context safely within AGENT_CONTEXT_CHARS')
    return value
