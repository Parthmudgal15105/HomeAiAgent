import asyncio

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.main import create_app
from backend.app.models import Incident
from backend.app.schemas import Decision


def test_api_authentication_and_sensitive_input_redaction(system):
    settings, sessions, gateway, agent, _, _ = system
    app = create_app(settings, sessions=sessions, gateway=gateway, llm=agent.llm)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/incidents').status_code == 401
        assert client.get('/api/incidents', headers={'Authorization': 'Bearer wrong'}).status_code == 401
        headers = {'Authorization': 'Bearer test-operator-token'}
        response = client.post('/api/incidents', headers=headers, json={'title': 'CodeDuel is down', 'description': 'password=unittest-secret'})
        assert response.status_code == 201
        body = response.json()
        assert 'unittest-secret' not in response.text
        assert body['status'] == 'OPEN'
        assert client.get('/api/incidents/' + body['id'], headers=headers).json()['id'] == body['id']
        assert client.get('/api/incidents', headers=headers).json()['total'] == 2


@pytest.mark.asyncio
async def test_api_background_investigation_reaches_evidence_backed_diagnosis(system):
    settings, sessions, gateway, _, _, incident_id = system
    class Provider:
        async def decide_next_action(self, context):
            if not context['observations']:
                return Decision(decision_type='TOOL_CALL', tool='docker_list')
            return Decision(decision_type='DIAGNOSIS', root_cause='Sandbox container exited', confidence=.8, evidence_observation_ids=[context['observations'][0]['id']])
    app = create_app(settings, sessions=sessions, gateway=gateway, llm=Provider())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'Authorization': 'Bearer test-operator-token'}) as client:
        response = await client.post(f'/api/incidents/{incident_id}/investigate')
        assert response.status_code == 202
        for _ in range(30):
            await asyncio.sleep(.01)
            body = (await client.get(f'/api/incidents/{incident_id}')).json()
            if body['status'] != 'INVESTIGATING':
                break
        assert body['root_cause'] == 'Sandbox container exited'
        assert body['agent_state']['phase'] == 'DIAGNOSED'
        assert body['status'] == 'OPEN'  # Diagnosed does not mean recovered.
        assert body['observations']


@pytest.mark.asyncio
async def test_api_background_provider_failure_is_persisted(system):
    settings, sessions, gateway, _, _, incident_id = system
    class BrokenProvider:
        async def decide_next_action(self, context):
            raise ValueError('Local model is unavailable')
    app = create_app(settings, sessions=sessions, gateway=gateway, llm=BrokenProvider())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'Authorization': 'Bearer test-operator-token'}) as client:
        assert (await client.post(f'/api/incidents/{incident_id}/investigate')).status_code == 202
        for _ in range(30):
            await asyncio.sleep(.01)
            body = (await client.get(f'/api/incidents/{incident_id}')).json()
            if body['status'] == 'FAILED':
                break
        assert body['status'] == 'FAILED'
        assert 'unavailable' in body['summary']


def test_restart_marks_inflight_work_interrupted_without_replay(system):
    settings, sessions, gateway, agent, _, incident_id = system
    with sessions() as session:
        session.get(Incident, incident_id).status = 'VERIFYING'
        session.commit()
    with TestClient(create_app(settings, sessions=sessions, gateway=gateway, llm=agent.llm)):
        pass
    assert not gateway.calls
    with sessions() as session:
        incident = session.get(Incident, incident_id)
        assert incident.status == 'FAILED'
        assert incident.agent_state['phase'] == 'INTERRUPTED'
