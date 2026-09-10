import json

import pytest

from backend.app.agent import Agent
from backend.app.config import Settings
from backend.app.db import Base, make_database
from backend.app.models import Incident
from backend.app.schemas import Decision
from backend.app.service import IncidentService


REGISTRY = {
    name: {'name': name, 'description': name, 'risk_level': risk, 'parameters': {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}}
    for name, risk, properties in [
        ('docker_list', 'READ_ONLY', {}),
        ('docker_inspect', 'READ_ONLY', {'container': {'type': 'string', 'enum': ['sandbox']}}),
        ('docker_logs', 'READ_ONLY', {'container': {'type': 'string', 'enum': ['sandbox']}, 'lines': {'type': 'integer', 'minimum': 1, 'maximum': 500}}),
        ('http_check', 'READ_ONLY', {'url': {'type': 'string', 'enum': ['http://127.0.0.1:9999/health']}}),
        ('restart_container', 'LOW_RISK_WRITE', {'container': {'type': 'string', 'enum': ['sandbox']}}),
        ('start_container', 'LOW_RISK_WRITE', {'container': {'type': 'string', 'enum': ['sandbox']}}),
    ]
}


class FakeGateway:
    def __init__(self):
        self.calls = []
        self.recovered = False

    async def registry(self):
        return REGISTRY

    async def execute(self, tool, arguments, approval=None):
        self.calls.append((tool, arguments, approval))
        if tool in ('restart_container', 'start_container'):
            assert approval and approval['approval_status'] == 'APPROVED'
            self.recovered = True
            result = {'restarted': True}
        elif tool == 'http_check':
            result = {'reachable': True, 'status_code': 200 if self.recovered else 502}
        elif tool == 'docker_inspect':
            result = {'state': 'running' if self.recovered else 'exited', 'health': 'healthy' if self.recovered else 'unhealthy'}
        else:
            result = {'containers': [{'name': 'sandbox', 'state': 'exited'}]}
        return {'tool': tool, 'ok': True, 'result': result, 'duration_ms': 1}


class StopProvider:
    async def decide_next_action(self, context):
        return Decision(decision_type='STOP', reason='Test completed')


@pytest.fixture
def system(tmp_path):
    topology = tmp_path / 'topology.json'
    topology.write_text(json.dumps({'services': {'codeduel': {'depends_on': ['sandbox'], 'health_checks': [{'tool': 'http_check', 'arguments': {'url': 'http://127.0.0.1:9999/health'}, 'expect': {'status_code': 200, 'reachable': True}}]}, 'sandbox': {'health_checks': [{'tool': 'docker_inspect', 'arguments': {'container': 'sandbox'}, 'expect': {'state': 'running', 'health': 'healthy'}}]}}}))
    settings = Settings(_env_file=None, database_url='sqlite:///:memory:', topology_path=str(topology), rag_enabled=False, aiops_api_token='test-operator-token', enable_write_actions=True, gateway_approval_secret='test-signing-secret')
    engine, sessions = make_database(settings.database_url)
    Base.metadata.create_all(engine)
    gateway = FakeGateway()
    agent = Agent(settings, sessions, gateway, StopProvider())
    service = IncidentService(settings, sessions, agent, gateway)
    with sessions() as session:
        incident = Incident(title='Sandbox API is down', service='codeduel')
        session.add(incident)
        session.commit()
        incident_id = incident.id
    yield settings, sessions, gateway, agent, service, incident_id
    engine.dispose()
