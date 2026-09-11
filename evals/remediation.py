"""Actual local LLM + mocked Redis recovery + real incident database/local RAG.

Run on the server: python -m evals.remediation --approve-mock --output /tmp/result.json
Only the in-memory fixture can change. No production diagnostic gateway is called.
The explicit flag authorizes the one simulated action for this acceptance test.
"""
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time

from sqlalchemy import select

from backend.app.agent import Agent, asdict
from backend.app.config import Settings
from backend.app.db import make_database
from backend.app.gateway import validate_tool
from backend.app.llm import OllamaLLMProvider
from backend.app.models import Incident
from backend.app.rag import LocalRAG
from backend.app.service import IncidentService
from .mock_gateway import MockDiagnosticGateway, WRITE_TOOLS
from .scenarios import HEALTHY_FIXTURES, SYNTHETIC_TOPOLOGY


class RecoverableRedis(MockDiagnosticGateway):
    def __init__(self):
        super().__init__('redis_down')
        self.recovered = False
        self.consumed: set[str] = set()

    async def registry(self):
        registry = await super().registry()
        registry = {k: v for k, v in registry.items() if k not in WRITE_TOOLS or k == 'start_container'}
        registry['start_container']['parameters']['properties']['container']['enum'] = ['redis']
        return registry

    async def execute(self, tool, arguments, approval=None):
        if tool == 'start_container':
            validate_tool(await self.registry(), tool, arguments, allow_write=True)
            if not approval or approval.get('approval_status') != 'APPROVED' or not approval.get('executed_at'):
                raise PermissionError('Persisted approval required for mocked write')
            if approval['id'] in self.consumed:
                raise PermissionError('Mocked action already consumed')
            self.consumed.add(approval['id'])
            self.calls.append({'tool': tool, 'arguments': arguments, 'simulated': True})
            self.recovered = True
            return {'ok': True, 'result': {'simulated': True, 'started': 'redis'}, 'duration_ms': 0.1}
        if self.recovered:
            validate_tool(await self.registry(), tool, arguments)
            for fixture in HEALTHY_FIXTURES:
                if fixture.matches(tool, arguments):
                    self.calls.append({'tool': tool, 'arguments': arguments, 'simulated': True})
                    return {'ok': True, 'result': deepcopy(fixture.result), 'duration_ms': 0.1}
            raise ValueError('No healthy fixture for requested diagnostic')
        return await super().execute(tool, arguments, approval)


async def run(settings: Settings, output: Path, approve: bool):
    if not approve:
        raise ValueError('--approve-mock is required; no real infrastructure writes occur')
    if not settings.database_url.startswith('postgresql'):
        raise ValueError('Run with deployed PostgreSQL settings to verify persistence')
    topology = deepcopy(SYNTHETIC_TOPOLOGY)
    topology['services']['redis']['health_checks'] = [{'tool': 'docker_inspect', 'arguments': {'container': 'redis'}, 'expect': {'state': 'running', 'health': 'healthy'}}]
    topology['services']['codeduel-api']['health_checks'] = [{'tool': 'http_check', 'arguments': {'url': 'http://127.0.0.1:3001/health'}, 'expect': {'reachable': True, 'status_code': 200}}]
    topology['services']['codeduel-public']['health_checks'] = [{'tool': 'http_check', 'arguments': {'url': 'https://codeduel.online'}, 'expect': {'reachable': True, 'status_code': 200}}]
    engine, sessions = make_database(settings.database_url)
    gateway = RecoverableRedis()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='aiops-mock-recovery-') as directory:
        path = Path(directory) / 'topology.json'
        path.write_text(json.dumps(topology))
        isolated = settings.model_copy(update={'topology_path': str(path), 'enable_write_actions': True})
        rag = LocalRAG(isolated)
        agent = Agent(isolated, sessions, gateway, OllamaLLMProvider(isolated), rag)
        service = IncidentService(isolated, sessions, agent, gateway, rag)
        with sessions() as session:
            incident = Incident(title='[SYNTHETIC ACCEPTANCE] Application submissions stuck', description=gateway.scenario.symptom + ' Investigate current fixture evidence and propose an allowed recovery action if appropriate. This is a simulated outage, not a real server incident.', service='codeduel-public', agent_state={'synthetic_fixture': True})
            session.add(incident); session.commit(); incident_id = incident.id
        await agent.investigate(incident_id)
        with sessions() as session:
            incident = session.get(Incident, incident_id)
            result = {'model': isolated.ollama_model, 'incident_id': incident_id, 'synthetic_tools': True, 'real_llm': True, 'database': 'PostgreSQL', 'before_approval': asdict(incident), 'actions': [asdict(a) for a in incident.actions]}
            actions = [a.id for a in incident.actions if a.approval_status == 'PENDING']
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str))
        if len(actions) != 1:
            raise ValueError('Local model did not produce exactly one safe pending action; report retained')
        result['approval_result'] = await service.approve(actions[0])
        try:
            await service.approve(actions[0])
            result['replay_rejected'] = False
        except ValueError:
            result['replay_rejected'] = True
        with sessions() as session:
            incident = session.get(Incident, incident_id)
            result['after_approval'] = asdict(incident)
            result['observations'] = [asdict(o) for o in incident.observations]
            result['hypotheses'] = [asdict(h) for h in incident.hypotheses]
        found = await rag.retrieve('Synthetic acceptance application submissions stuck Redis container stopped and recovered')
        result['history_retrieved'] = any(d.get('incident_id') == incident_id for d in found)
        result['simulated_write_count'] = len(gateway.consumed)
        result['seconds'] = round(time.monotonic() - started, 3)
        result['passed'] = result['after_approval']['status'] == 'RESOLVED' and result['replay_rejected'] and result['history_retrieved'] and result['simulated_write_count'] == 1
        output.write_text(json.dumps(result, indent=2, default=str))
        print(json.dumps({k: result[k] for k in ('incident_id', 'model', 'passed', 'history_retrieved', 'replay_rejected', 'simulated_write_count', 'seconds')}, indent=2))
    engine.dispose()
    return result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-mock', action='store_true')
    parser.add_argument('--model')
    parser.add_argument('--output', type=Path, default=Path('/tmp/aiops-real-model-mocked-recovery.json'))
    args = parser.parse_args()
    settings = Settings(**({'ollama_model': args.model} if args.model else {}))
    raise SystemExit(0 if asyncio.run(run(settings, args.output, args.approve_mock)) else 1)
