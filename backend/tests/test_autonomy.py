import json

import pytest

from backend.app.models import Incident
from backend.tests.conftest import REGISTRY


@pytest.mark.asyncio
async def test_autonomous_start_is_scoped_verified_and_not_retried(system, tmp_path):
    settings, sessions, gateway, agent, service, incident_id = system
    settings.enable_autonomous_actions = True
    profile = tmp_path / 'autonomous-topology.json'
    profile.write_text(json.dumps({'services': {
        'codeduel': {'depends_on': ['sandbox'], 'health_checks': [
            {'tool': 'http_check', 'arguments': {'url': 'http://127.0.0.1:9999/health'},
             'expect': {'status_code': 200}}]},
        'sandbox': {'containers': ['sandbox'], 'health_checks': [
            {'tool': 'docker_inspect', 'arguments': {'container': 'sandbox'},
             'expect': {'state.running': True, 'health': 'healthy'}}]}}}))
    settings.topology_path = str(profile)

    async def execute(tool, arguments, approval=None):
        gateway.calls.append((tool, arguments, approval))
        if tool == 'start_container':
            assert approval['approval_status'] == 'AUTO_AUTHORIZED'
            gateway.recovered = True
            return {'ok': True, 'result': {'execution_succeeded': True}}
        return {'ok': True, 'result': {'state': {'running': gateway.recovered},
                                       'health': 'healthy' if gateway.recovered else 'unhealthy'}}

    gateway.execute = execute
    precheck = await gateway.execute('docker_inspect', {'container': 'sandbox'})
    agent.record_observation(incident_id, 'docker_inspect', {'container': 'sandbox'}, precheck)
    result = await service.execute_autonomous(incident_id, 'start_container', {'container': 'sandbox'}, 'Stopped sandbox')
    assert result['verification_status'] == 'PASSED'
    assert result['requires_approval'] is False
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert len(incident.actions) == 1
        assert any(o.phase == 'VERIFICATION' for o in incident.observations)
    with pytest.raises(ValueError, match='already attempted'):
        await service.execute_autonomous(incident_id, 'start_container', {'container': 'sandbox'}, 'Retry')
    with pytest.raises(ValueError, match='autonomous stop'):
        await service.execute_autonomous(incident_id, 'stop_container', {'container': 'sandbox'}, 'Stop')


@pytest.mark.asyncio
async def test_autonomous_unknown_target_rejected(system, tmp_path):
    settings, _, gateway, agent, service, incident_id = system
    settings.enable_autonomous_actions = True
    profile = tmp_path / 'autonomous-topology.json'
    profile.write_text(json.dumps({'services': {'codeduel': {'health_checks': []}}}))
    settings.topology_path = str(profile)
    agent.record_observation(incident_id, 'docker_inspect', {'container': 'sandbox'},
                             {'ok': True, 'result': {'state': {'running': False}}})
    with pytest.raises(ValueError, match='outside this application'):
        await service.execute_autonomous(incident_id, 'start_container', {'container': 'sandbox'}, 'Unknown target')
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_manual_only_gateway_action_cannot_run_autonomously(system, tmp_path):
    settings, _, gateway, agent, service, incident_id = system
    settings.enable_autonomous_actions = True
    profile = tmp_path / 'manual-topology.json'
    profile.write_text(json.dumps({'services': {'codeduel': {'containers': ['sandbox'], 'health_checks': [
        {'tool': 'docker_inspect', 'arguments': {'container': 'sandbox'}, 'expect': {'state.running': True}}]}}}))
    settings.topology_path = str(profile)
    async def manual_registry():
        return {**REGISTRY, 'start_container': {**REGISTRY['start_container'], 'autonomous_targets': []}}
    gateway.registry = manual_registry
    agent.record_observation(incident_id, 'docker_inspect', {'container': 'sandbox'},
                             {'ok': True, 'result': {'state': {'running': False}}})
    with pytest.raises(ValueError, match='manual approval'):
        await service.execute_autonomous(incident_id, 'start_container', {'container': 'sandbox'}, 'Manual-only target')
    assert not any(call[0] == 'start_container' for call in gateway.calls)
