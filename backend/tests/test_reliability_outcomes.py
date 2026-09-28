import asyncio
import json
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.failures import FailureKind, model_failure_kind, tool_failure_kind
from backend.app.llm import decision_schema, model_prompt_context, ollama_prompt_tokens
from backend.app.models import Incident
from backend.app.schemas import Decision
from diagnostic_gateway.config import GatewayConfig
from diagnostic_gateway.tools import DiagnosticTools


ROOT = Path(__file__).resolve().parents[2]


def test_failure_categories_are_stable_and_non_overlapping():
    assert model_failure_kind(asyncio.TimeoutError()) == FailureKind.MODEL_TIMEOUT
    assert model_failure_kind(ValueError('invalid JSON')) == FailureKind.MODEL_INVALID_OUTPUT
    assert model_failure_kind(ValueError('provider unavailable')) == FailureKind.MODEL_UNAVAILABLE
    assert tool_failure_kind(asyncio.TimeoutError()) == FailureKind.TOOL_TIMEOUT
    assert tool_failure_kind('gateway command timed out') == FailureKind.TOOL_TIMEOUT
    assert tool_failure_kind('permission denied') == FailureKind.TOOL_FAILURE


def test_ollama_prompt_uses_terse_catalog_but_keeps_schema_constraints(system):
    settings, _, _, agent, _, incident_id = system
    settings.topology_path = str(ROOT / 'config/topology.json')
    config = GatewayConfig.model_validate_json((ROOT / 'config/gateway.json').read_text())
    registry = {entry['name']: entry for entry in DiagnosticTools(config).metadata()}
    context = agent.context(incident_id, registry)
    prompt = model_prompt_context(context)
    assert all('parameters' not in tool for tool in prompt['tools'])
    assert set(prompt['topology']['services']) == {
        'codeduel', 'cloudflare', 'codeduel-proxy', 'codeduel-api', 'codeduel-worker',
        'codeduel-frontend', 'redis', 'mongodb-atlas', 'docker', 'host',
    }
    schema = decision_schema(context)
    docker_schema = json.dumps(schema)
    assert 'codeduel-api-1' in docker_schema
    content = json.dumps(prompt, separators=(',', ':'))
    # The configured output allowance must fit the deliberately reduced context.
    assert ollama_prompt_tokens(content, schema) + settings.ollama_num_predict <= settings.ollama_num_ctx


@pytest.mark.asyncio
async def test_missing_capability_escalates_and_is_persisted(system):
    _, sessions, _, agent, _, incident_id = system

    class Provider:
        async def decide_next_action(self, _context):
            return Decision(
                decision_type='NEED_USER_INPUT', reason='Atlas TLS reachability is not configured.',
                summary='External Atlas is implicated but not directly inspectable.',
                capability_status='MISSING_TOOL', capability_gap='mongodb_atlas_connectivity',
                missing_capability='A bounded Atlas SRV/TLS reachability diagnostic.',
                recommended_next_check='Resolve the Atlas SRV record and test a returned shard TLS handshake.',
            )

    agent.llm = Provider()
    await agent.investigate(incident_id)
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status == 'ESCALATED'
        assert incident.agent_state['phase'] == 'ESCALATED'
        assert incident.agent_state['capability_gaps'] == ['mongodb_atlas_connectivity']
        assert incident.report['capability_status'] == 'MISSING_TOOL'
        assert incident.report['recommended_next_check'].startswith('Resolve')


@pytest.mark.asyncio
async def test_model_and_tool_failures_are_persisted_with_distinct_categories(system):
    _, sessions, gateway, agent, _, incident_id = system

    class TimeoutProvider:
        async def decide_next_action(self, _context):
            raise asyncio.TimeoutError()

    agent.llm = TimeoutProvider()
    await agent.investigate(incident_id)
    with sessions() as session:
        assert session.get(Incident, incident_id).agent_state['failure']['kind'] == 'MODEL_TIMEOUT'

    with sessions() as session:
        second = Incident(title='Tool timeout', service='codeduel')
        session.add(second)
        session.commit()
        second_id = second.id

    async def timeout_tool(tool, arguments, approval=None):
        if tool == 'docker_list':
            raise asyncio.TimeoutError()
        return await gateway.execute(tool, arguments, approval)

    class ToolThenStop:
        async def decide_next_action(self, context):
            if not context['observations']:
                return Decision(decision_type='TOOL_CALL', tool='docker_list', reason='Test timeout')
            return Decision(decision_type='STOP', reason='Do not infer an outage from a failed diagnostic.')

    original = gateway.execute
    gateway.execute = timeout_tool
    agent.llm = ToolThenStop()
    await agent.investigate(second_id)
    gateway.execute = original
    with sessions() as session:
        observation = session.get(Incident, second_id).observations[0]
        assert observation.raw_result['failure_kind'] == 'TOOL_TIMEOUT'
