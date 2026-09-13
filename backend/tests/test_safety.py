import asyncio
import json

import pytest
from jsonschema.exceptions import ValidationError

from backend.app.gateway import DiagnosticGateway, validate_tool
from backend.app.llm import parse_decision
from backend.app.models import Hypothesis, Incident
from backend.app.safety import disk_severity, redact
from backend.app.schemas import Decision, HypothesisUpdate
from conftest import REGISTRY


@pytest.mark.parametrize('tool,args', [
    ('run_shell', {'command': 'id'}),
    ('restart_container', {'container': 'sandbox'}),
    ('docker_inspect', {'container': 'production'}),
    ('docker_inspect', {'container': 'sandbox', 'command': 'id'}),
    ('docker_logs', {'container': 'sandbox', 'lines': 501}),
    ('http_check', {'url': 'http://169.254.169.254/latest/meta-data'}),
])
def test_allowlists_and_schemas_reject_unsafe_call(tool, args):
    with pytest.raises((ValueError, ValidationError)):
        validate_tool(REGISTRY, tool, args)


def test_redaction_handles_recursive_credentials():
    safe = redact({'api_token': 'abc', 'logs': ['postgres://user:p4ss@localhost/db password=hunter2 Bearer xyz.ABC.123'], 'nested': {'Authorization': 'Basic abc'}, 'key': '-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----'}) # secret-scan: fixture
    rendered = json.dumps(safe)
    for secret in ('hunter2', 'p4ss', 'xyz.ABC.123', 'Basic abc', '\\nsecret'):
        assert secret not in rendered
    assert safe['api_token'] == '[REDACTED]'
    assert 'sensitive' not in redact('cloudflared --token sensitive tskey-auth-sensitive sessionID=sensitive')
    assert 'quoted secret' not in redact('cloudflared --token "quoted secret"')
    assert 'abcdefghijklmnopqrstuvwx' not in redact('eyJabcdefghijklmnopqrstuvwxabcdefghijklmnopqrstuvwx')


@pytest.mark.parametrize('percent,expected', [(79.9, 'normal'), (80, 'warning'), (90, 'high'), (95, 'high'), (95.1, 'critical')])
def test_disk_thresholds_are_deterministic(percent, expected):
    assert disk_severity(percent) == expected


def test_model_json_is_strict_and_never_evaluated():
    assert parse_decision('```json\n{"decision_type":"STOP"}\n```').decision_type == 'STOP'
    for raw in ('__import__("os").system("id")', '{"decision_type":"TOOL_CALL","tool":"docker_list","command":"id"}', '{"decision_type":"DIAGNOSIS","root_cause":"Redis down"}'):
        with pytest.raises(ValueError):
            parse_decision(raw)


def test_evidence_and_hypotheses_must_belong_to_incident(system):
    _, sessions, _, agent, _, incident_id = system
    oid = agent.record_observation(incident_id, 'docker_list', {}, {'ok': True, 'result': {'containers': []}})
    with pytest.raises(ValueError):
        agent.validate_evidence(incident_id, ['invented'])
    with sessions() as session:
        other = Incident(title='Other incident')
        session.add(other)
        session.commit()
        other_id = other.id
    with pytest.raises(ValueError):
        agent.validate_evidence(other_id, [oid])
    update = HypothesisUpdate(description='Container stopped', confidence=.8, status='SUPPORTED', supporting_observation_ids=[oid])
    agent.update_hypotheses(incident_id, [update])
    with sessions() as session:
        hypothesis = session.query(Hypothesis).one()
        assert hypothesis.supporting_observation_ids == [oid]
    with pytest.raises(ValueError):
        agent.update_hypotheses(other_id, [update])


def test_transport_failure_not_root_cause_evidence(system):
    _, _, _, agent, _, incident_id = system
    oid = agent.record_observation(incident_id, 'docker_list', {}, {'ok': False, 'result': {}, 'error': 'Gateway unauthorized'})
    with pytest.raises(ValueError, match='transport'):
        agent.validate_evidence(incident_id, [oid])


@pytest.mark.asyncio
async def test_duplicate_protection_and_bounded_invalid_decisions(system):
    _, sessions, gateway, agent, _, incident_id = system
    class DuplicateProvider:
        async def decide_next_action(self, context):
            return Decision(decision_type='TOOL_CALL', tool='docker_list', arguments={})
    agent.llm = DuplicateProvider()
    await agent.investigate(incident_id)
    assert len(gateway.calls) == 1
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status == 'FAILED'
        assert incident.agent_state['validation_failures'] == 3
        assert len(incident.observations) == 1


@pytest.mark.asyncio
async def test_invalid_hypothesis_metadata_does_not_block_safe_diagnostic(system):
    _, sessions, gateway, agent, _, incident_id = system
    contexts = []

    class Provider:
        async def decide_next_action(self, context):
            contexts.append(context)
            if not context['observations']:
                return Decision(
                    decision_type='TOOL_CALL', tool='docker_list', arguments={},
                    hypothesis_updates=[HypothesisUpdate(description='Container is healthy', confidence=.8, status='ELIMINATED')],
                )
            return Decision(decision_type='STOP', reason='Test complete')

    agent.llm = Provider()
    await agent.investigate(incident_id)
    assert len(gateway.calls) == 1
    assert 'Hypothesis update ignored' in contexts[1]['validation_feedback']
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status == 'OPEN'
        assert len(incident.observations) == 1
        assert list(incident.hypotheses) == []


@pytest.mark.asyncio
async def test_agent_never_executes_unapproved_model_write(system):
    _, sessions, gateway, agent, _, incident_id = system
    class UnsafeProvider:
        async def decide_next_action(self, context):
            return Decision(decision_type='TOOL_CALL', tool='restart_container', arguments={'container': 'sandbox'})
    agent.llm = UnsafeProvider()
    await agent.investigate(incident_id)
    assert gateway.calls == []
    with sessions() as session:
        assert session.get(Incident, incident_id).status == 'FAILED'


@pytest.mark.asyncio
async def test_total_runtime_cancels_hung_model(system):
    settings, sessions, _, agent, _, incident_id = system
    settings.agent_max_runtime_seconds = 1
    class HungProvider:
        async def decide_next_action(self, context):
            await asyncio.sleep(30)
    agent.llm = HungProvider()
    await agent.investigate(incident_id)
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status == 'FAILED'
        assert 'runtime limit' in incident.summary


@pytest.mark.asyncio
async def test_gateway_enforces_approval_before_network(system):
    settings, _, _, _, _, _ = system
    gateway = DiagnosticGateway(settings)
    gateway._registry = REGISTRY
    with pytest.raises(ValueError):
        await gateway.execute('restart_container', {'container': 'sandbox'})
    with pytest.raises(ValueError):
        await gateway.execute('restart_container', {'container': 'sandbox'}, approval={'id': 'fake', 'approval_status': 'PENDING'})
