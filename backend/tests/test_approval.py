import asyncio
import json
from datetime import timedelta

import pytest

from backend.app.models import Action, Incident, now
from backend.app.schemas import Decision, Remediation
from backend.app.service import matches
from conftest import REGISTRY


def diagnose(agent, incident_id):
    oid = agent.record_observation(incident_id, 'docker_inspect', {'container': 'sandbox'}, {'ok': True, 'result': {'state': 'exited'}})
    agent.save_diagnosis(incident_id, Decision(decision_type='DIAGNOSIS', root_cause='Sandbox container exited', confidence=.99, evidence_observation_ids=[oid], summary='Container is stopped.', remediation=[Remediation(tool='restart_container', arguments={'container': 'sandbox'}, reason='Restore the sandbox process')]), REGISTRY)


@pytest.mark.asyncio
async def test_approval_is_persisted_and_recovery_checked(system):
    _, sessions, gateway, agent, service, incident_id = system
    diagnose(agent, incident_id)
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status == 'WAITING_FOR_APPROVAL'
        assert incident.root_cause_confidence == .4  # One diagnostic family has a conservative ceiling.
        action_id = incident.actions[0].id
    assert gateway.calls == []
    result = await service.approve(action_id)
    assert result['approval_status'] == 'APPROVED'
    assert result['verification_status'] == 'PASSED'
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status == 'RESOLVED'
        assert incident.resolved_at
        assert len([o for o in incident.observations if o.phase == 'VERIFICATION']) == 2
    assert gateway.calls[0][2]['executed_at']
    with pytest.raises(ValueError):
        await service.approve(action_id)
    assert len([c for c in gateway.calls if c[0] == 'restart_container']) == 1


@pytest.mark.asyncio
async def test_concurrent_approvals_execute_at_most_once(system):
    _, sessions, gateway, agent, service, incident_id = system
    diagnose(agent, incident_id)
    with sessions() as session:
        action_id = session.get(Incident, incident_id).actions[0].id
    results = await asyncio.gather(service.approve(action_id), service.approve(action_id), return_exceptions=True)
    assert sum(isinstance(r, ValueError) for r in results) == 1
    assert len([c for c in gateway.calls if c[0] == 'restart_container']) == 1


@pytest.mark.asyncio
async def test_recovery_failure_does_not_resolve(system):
    _, sessions, _, agent, service, incident_id = system
    diagnose(agent, incident_id)
    result = await service.verify(incident_id)
    assert not result['verified']
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status != 'RESOLVED'
        assert not incident.resolved_at


@pytest.mark.asyncio
async def test_missing_topology_never_resolves(system):
    settings, sessions, gateway, agent, service, incident_id = system
    diagnose(agent, incident_id)
    gateway.recovered = True
    settings.topology_path = '/definitely/missing/topology.json'
    result = await service.verify(incident_id)
    assert result['verified'] is False
    assert gateway.calls == []
    with sessions() as session:
        assert session.get(Incident, incident_id).status != 'RESOLVED'


@pytest.mark.asyncio
async def test_approval_blocks_missing_target_verification_before_write(system, tmp_path):
    settings, sessions, gateway, agent, service, incident_id = system
    diagnose(agent, incident_id)
    path = tmp_path / 'partial-topology.json'
    path.write_text(json.dumps({'services': {'codeduel': {'health_checks': [{'tool': 'http_check', 'arguments': {'url': 'http://127.0.0.1:9999/health'}, 'expect': {'status_code': 200}}]}}}))
    settings.topology_path = str(path)
    with sessions() as session:
        action_id = session.get(Incident, incident_id).actions[0].id
    with pytest.raises(ValueError, match='remediation target'):
        await service.approve(action_id)
    assert gateway.calls == []
    with sessions() as session:
        assert session.get(Action, action_id).approval_status == 'PENDING'


def test_rejecting_other_pending_action_preserves_active_verification(system):
    _, sessions, _, agent, service, incident_id = system
    diagnose(agent, incident_id)
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        action_id = incident.actions[0].id
        incident.status = 'VERIFYING'
        session.commit()
    service.reject(action_id)
    with sessions() as session:
        assert session.get(Incident, incident_id).status == 'VERIFYING'


@pytest.mark.asyncio
async def test_expired_or_rejected_actions_never_execute(system):
    _, sessions, gateway, agent, service, incident_id = system
    diagnose(agent, incident_id)
    with sessions() as session:
        action = session.get(Incident, incident_id).actions[0]
        action_id = action.id
        action.expires_at = now() - timedelta(seconds=1)
        session.commit()
    with pytest.raises(ValueError, match='expired'):
        await service.approve(action_id)
    with sessions() as session:
        assert session.get(Action, action_id).approval_status == 'EXPIRED'
        assert session.get(Incident, incident_id).status == 'OPEN'
    diagnose(agent, incident_id)
    with sessions() as session:
        next_id = session.get(Incident, incident_id).actions[-1].id
    service.reject(next_id)
    with pytest.raises(ValueError):
        await service.approve(next_id)
    assert gateway.calls == []


def test_verifier_is_strict_about_missing_values_and_boolean_types():
    assert matches({'status': {'ready': True}}, {'status.ready': True})
    assert not matches({'status': {'ready': 1}}, {'status.ready': True})
    assert not matches({'status': {}}, {'status.ready': True})
