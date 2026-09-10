from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from backend.app.context import compact_context, compact_schema, sampled, size
from backend.app.models import Incident
from diagnostic_gateway.config import GatewayConfig
from diagnostic_gateway.tools import DiagnosticTools

ROOT = Path(__file__).resolve().parents[2]


def test_real_topology_and_gateway_log_context_fit_budget_without_losing_ids(system):
    settings, sessions, _, agent, _, incident_id = system
    settings.topology_path = str(ROOT / 'config/topology.json')
    config = GatewayConfig.model_validate_json((ROOT / 'config/gateway.json').read_text())
    # Construct metadata only: no commands, sockets, or host diagnostics execute.
    registry = {entry['name']: entry for entry in DiagnosticTools(config).metadata()}
    untouched = deepcopy(registry)
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        incident.agent_state = {'retrieved_runbooks': [{'kind': 'runbook', 'text': 'Local runbook guidance. ' * 200, 'source': 'test'} for _ in range(4)]}
        session.commit()
    ids = []
    for step in range(18):
        ids.append(agent.record_observation(incident_id, 'docker_logs', {'container': 'codeduel-api-1', 'lines': 100 + step}, {'ok': True, 'result': {'lines': [f'MongoServerSelectionError: database connection unavailable trace {index} ' + 'detail ' * 70 for index in range(100)]}}))
    context = agent.context(incident_id, registry)
    assert size(context) <= settings.agent_context_chars
    assert [item['id'] for item in context['observations']] == ids
    assert all('MongoServerSelectionError' in json.dumps(item['result']) for item in context['observations'])
    assert context['observations'][0]['tool_arguments'] == {'container': 'codeduel-api-1', 'lines': 100}
    assert context['topology']['services']['codeduel-api']['depends_on'] == settings.topology()['services']['codeduel-api']['depends_on']
    assert registry == untouched  # Cached executor schemas are never mutated.
    compact = {tool['name']: tool for tool in context['tools']}
    for tool in registry:
        assert compact[tool]['parameters'] == compact_schema(registry[tool]['parameters'])
    # Exact target/port constraints, enum validation, bounds, and extra argument
    # denial must have identical semantics after annotation removal.
    samples = {
        'docker_inspect': [{'container': config.containers[0]}, {'container': 'unauthorized'}, {'container': config.containers[0], 'command': 'id'}],
        'docker_logs': [{'container': config.containers[0], 'lines': 100}, {'container': config.containers[0], 'lines': 501}],
        'port_check': [{'host': config.tcp_targets[0].host, 'port': config.tcp_targets[0].port}, {'host': config.tcp_targets[0].host, 'port': 65530}, {'host': '169.254.169.254', 'port': 80}],
        'http_check': [{'url': config.http_urls[0]}, {'url': 'http://169.254.169.254/latest/meta-data'}],
    }
    for name, arguments in samples.items():
        before = Draft202012Validator(registry[name]['parameters'])
        after = Draft202012Validator(compact[name]['parameters'])
        assert [before.is_valid(item) for item in arguments] == [after.is_valid(item) for item in arguments]


def test_schema_annotations_do_not_remove_named_properties_or_enum_object_keys():
    schema = {'type': 'object', 'title': 'Annotation', 'properties': {'title': {'type': 'string', 'title': 'Field label', 'default': 'x', 'minLength': 3}, 'default': {'enum': [{'title': 'Preserve this', 'default': 2}]}}, 'required': ['title'], 'additionalProperties': False}
    compact = compact_schema(schema)
    assert compact['properties']['title'] == {'type': 'string', 'minLength': 3}
    assert compact['properties']['default']['enum'] == [{'title': 'Preserve this', 'default': 2}]
    assert compact['required'] == ['title']
    assert compact['additionalProperties'] is False


def test_already_small_context_is_not_rewritten_and_oversize_fails_closed(system):
    _, _, _, agent, _, incident_id = system
    small = agent.context(incident_id, {})
    assert compact_context(small, 26000) is small
    impossible = deepcopy(small)
    impossible['tools'] = [{'parameters': {'type': 'object', 'properties': {'container': {'enum': ['container-' + str(index) for index in range(1000)]}}}, 'name': 'docker_inspect'}]
    with pytest.raises(ValueError, match='constraints'):
        compact_context(impossible, 1000)


def test_list_sampling_prioritizes_failed_targets_with_a_hard_item_limit():
    items = [{'name': str(index), 'state': 'running' if index < 10 else 'exited'} for index in range(20)]
    result = sampled(items, 100, 1)
    assert len(result) == 1
    assert result[0]['state'] == 'exited'
