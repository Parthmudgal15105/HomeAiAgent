"""Malformed or adversarial model output must never reach the tool executor."""
from types import SimpleNamespace
import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from backend.app.llm import OllamaLLMProvider, decision_schema, parse_decision
from backend.app.safety import evidence_confidence, redact
from conftest import REGISTRY


def test_completed_snapshots_are_removed_without_expanding_targets_or_writes():
    from copy import deepcopy
    from backend.app.llm import remaining_parameters
    registry = deepcopy(REGISTRY)
    context = {'tools': list(registry.values()), 'observations': [
        {'id': 'a', 'tool_name': 'docker_list', 'tool_arguments': {}},
        {'id': 'b', 'tool_name': 'docker_inspect', 'tool_arguments': {'container': 'sandbox'}},
    ]}
    validator = Draft202012Validator(decision_schema(context))
    call = {'reason': 'Another check', 'decision_type': 'TOOL_CALL', 'tool': 'docker_list', 'arguments': {}, 'hypothesis_updates': []}
    assert not validator.is_valid(call)
    assert not validator.is_valid({**call, 'tool': 'docker_inspect', 'arguments': {'container': 'sandbox'}})
    assert not validator.is_valid({**call, 'tool': 'docker_inspect', 'arguments': {'container': 'production'}})
    assert registry == REGISTRY
    write = {'name': 'start_container', 'risk_level': 'LOW_RISK_WRITE', 'parameters': REGISTRY['docker_inspect']['parameters']}
    assert remaining_parameters(write, [{'tool_name': 'start_container', 'arguments': {'container': 'sandbox'}}]) == write['parameters']


def test_log_sampling_changes_do_not_reopen_a_completed_target():
    from backend.app.llm import remaining_parameters
    tool = {'name': 'docker_logs', 'risk_level': 'READ_ONLY', 'parameters': {
        'type': 'object', 'properties': {'container': {'enum': ['api', 'queue']}, 'lines': {'type': 'integer', 'maximum': 100}},
        'required': ['container'], 'additionalProperties': False}}
    schema = remaining_parameters(tool, [{'tool_name': 'docker_logs', 'tool_arguments': {'container': 'api', 'lines': 10}}])
    validator = Draft202012Validator(schema)
    assert not validator.is_valid({'container': 'api', 'lines': 100})
    assert validator.is_valid({'container': 'queue', 'lines': 100})
    assert not validator.is_valid({'container': 'queue', 'lines': 101})


def test_extract_only_one_complete_object():
    assert parse_decision('Result:\n{"decision_type":"STOP","reason":"No evidence"}\nEnd.').decision_type == 'STOP'
    for text in ('{"decision_type":"STOP"} {"decision_type":"TOOL_CALL","tool":"docker_list"}',
                 '[{"decision_type":"STOP"}]',
                 '{"broken": {"decision_type":"STOP"}',
                 '{"decision_type":"STOP","unexpected":"shell"}', 'x' * 64001):
        with pytest.raises(ValueError):
            parse_decision(text)


def test_model_grammar_preserves_exact_tool_schema_and_owned_citations():
    context = {'tools': list(REGISTRY.values()), 'observations': [{'id': 'owned-id'}]}
    validator = Draft202012Validator(decision_schema(context))
    call = {'decision_type': 'TOOL_CALL', 'tool': 'docker_inspect', 'arguments': {'container': 'sandbox'}, 'reason': 'Check state', 'hypothesis_updates': []}
    assert validator.is_valid(call)
    for tool, arguments in [('docker_inspect', {'container': 'production'}), ('docker_list', {'command': 'id'}), ('restart_container', {'container': 'sandbox'}), ('shell', {})]:
        assert not validator.is_valid({**call, 'tool': tool, 'arguments': arguments})
    call['hypothesis_updates'] = [{'description': 'Container unavailable', 'confidence': .4, 'supporting_observation_ids': ['unowned']}]
    assert not validator.is_valid(call)


@pytest.mark.asyncio
async def test_second_invalid_model_output_fails_closed_and_records_metrics(system, monkeypatch):
    settings, *_ = system
    real = httpx.AsyncClient
    def handler(request):
        return httpx.Response(200, content=json.dumps({'message': {'content': '{bad'}, 'done': True}).encode() + b'\n')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    provider = OllamaLLMProvider(settings)
    with pytest.raises(ValueError, match='twice'):
        await provider.decide_next_action({'observations': []})
    assert provider.metrics['requests'] == 2
    assert provider.metrics['invalid_json'] == 2
    assert provider.metrics['retries'] == 1
    assert provider.metrics['failed_decisions'] == 1
    assert len(provider.metrics['first_token_ms']) == 2


@pytest.mark.asyncio
async def test_truncated_stream_does_not_execute_partial_decision(system, monkeypatch):
    settings, *_ = system
    real = httpx.AsyncClient
    def handler(request):
        return httpx.Response(200, content=json.dumps({'message': {'content': '{"decision_type":"STOP"}'}}).encode() + b'\n')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    provider = OllamaLLMProvider(settings)
    with pytest.raises(ValueError, match='before completion'):
        await provider.decide_next_action({'observations': []})
    assert provider.metrics['failed_decisions'] == 1


def observation(tool, result=None, ok=True):
    return SimpleNamespace(tool_name=tool, normalized_result=result or {}, raw_result={'ok': ok})


def test_confidence_increases_with_independent_evidence_and_decreases_with_conflicts():
    one = [observation('docker_list')]
    redundant = [*one, observation('docker_inspect')]
    independent = [*one, observation('port_check')]
    direct = [*independent, observation('docker_logs', {'output': 'ECONNREFUSED redis:6379'})]
    assert evidence_confidence([], .99)[0] == .15
    assert evidence_confidence(one, .99)[0] == evidence_confidence(redundant, .99)[0]
    assert evidence_confidence(independent, .99)[0] > evidence_confidence(one, .99)[0]
    assert evidence_confidence(direct, .99)[0] > evidence_confidence(independent, .99)[0]
    assert evidence_confidence(direct, .99, ['conflict'])[0] < evidence_confidence(direct, .99)[0]
    assert evidence_confidence(direct, .2)[0] == .2
    assert evidence_confidence(direct, .99)[1]['historical_context_weight'] == 0


@pytest.mark.parametrize('secret', [
    'Cookie: session=first-secret; csrf=second-secret',
    'Set-Cookie: sid=first-secret; refresh=second-secret; HttpOnly',
    'Authorization: Custom first-secret second-secret',
    'postgresql://first-secret:second-secret@database.invalid/private', # secret-scan: fixture
    'mongodb+srv://first-secret:second-secret@database.invalid/private', # secret-scan: fixture
    'redis://first-secret:second-secret@database.invalid/0', # secret-scan: fixture
])
def test_whole_headers_and_database_uris_are_redacted(secret):
    safe = redact(secret)
    assert 'first-secret' not in safe
    assert 'second-secret' not in safe
    assert 'database.invalid' not in safe
