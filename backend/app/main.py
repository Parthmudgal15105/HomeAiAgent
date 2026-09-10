import asyncio
from contextlib import asynccontextmanager
import hmac
import logging

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text, update

from .agent import Agent, asdict
from .config import Settings, get_settings
from .db import make_database
from .gateway import DiagnosticGateway
from .llm import OllamaLLMProvider
from .models import Action, AuditEvent, EvaluationRun, Incident, now
from .rag import LocalRAG
from .safety import redact
from .schemas import IncidentCreate
from .service import IncidentService
from .overview import Overview

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)


def create_app(settings: Settings | None = None, sessions=None, gateway=None, llm=None, rag=None) -> FastAPI:
    settings = settings or get_settings()
    engine = None
    if sessions is None:
        engine, sessions = make_database(settings.database_url)
    gateway = gateway or DiagnosticGateway(settings)
    llm = llm or OllamaLLMProvider(settings)
    rag = rag or (LocalRAG(settings) if settings.rag_enabled else None)
    agent = Agent(settings, sessions, gateway, llm, rag)
    service = IncidentService(settings, sessions, agent, gateway, rag)
    overview_service = Overview(settings, gateway)
    tasks: dict[str, asyncio.Task] = {}
    bearer = HTTPBearer(auto_error=False)

    async def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not settings.aiops_api_token:
            raise HTTPException(503, 'AIOPS_API_TOKEN is not configured; API access is disabled')
        if not credentials or not hmac.compare_digest(credentials.credentials.encode(), settings.aiops_api_token.encode()):
            raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Bearer'})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Single-worker deployment: interrupted read investigations are safely marked failed.
        # Writes were durably claimed before dispatch and are NEVER replayed on startup.
        with sessions() as session:
            for incident in session.scalars(select(Incident).where(Incident.status.in_(['INVESTIGATING', 'VERIFYING']))):
                incident.status = 'FAILED'
                incident.agent_state = {**incident.agent_state, 'phase': 'INTERRUPTED', 'error': 'Backend restarted during work. Inspect evidence and explicitly retry diagnostics or verification.'}
            session.commit()
        yield
        for task in tasks.values():
            task.cancel()
        if tasks:
            await asyncio.gather(*list(tasks.values()), return_exceptions=True)
        if engine:
            engine.dispose()

    app = FastAPI(title='Local Home-Lab Operator', version='1.0.0', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sessions, app.state.agent, app.state.service = sessions, agent, service
    router = APIRouter(prefix='/api', dependencies=[Depends(authenticate)])

    def detail(incident_id: str) -> dict:
        with sessions() as session:
            incident = session.get(Incident, incident_id)
            if not incident:
                raise HTTPException(404, 'Incident not found')
            events = list(session.scalars(select(AuditEvent).where(AuditEvent.incident_id == incident_id).order_by(AuditEvent.created_at)))
            return {**asdict(incident), 'observations': [asdict(o) for o in incident.observations], 'hypotheses': [asdict(h) for h in incident.hypotheses], 'actions': [asdict(a) for a in incident.actions], 'audit_events': [asdict(e) for e in events]}

    @app.get('/health')
    @app.get('/healthz')
    async def health():
        try:
            with sessions() as session:
                session.execute(text('SELECT 1'))
            return {'status': 'ok', 'service': 'homeai-backend'}
        except Exception:
            raise HTTPException(503, 'Database unavailable')

    @router.get('/health')
    async def stack_health():
        targets = {'gateway': settings.gateway_url.rstrip('/') + '/healthz', 'ollama': settings.ollama_base_url.rstrip('/') + '/api/tags', 'qdrant': settings.qdrant_url.rstrip('/') + '/readyz'}
        async def check(name, url):
            try:
                async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    result = {'status': 'ok'}
                    if name == 'ollama':
                        models = [m['name'] for m in response.json().get('models', [])]
                        result.update({'models': models, 'reasoning_model': settings.ollama_model, 'embedding_model': settings.ollama_embedding_model, 'reasoning_model_loaded': settings.ollama_model in models})
                    return name, result
            except Exception as exc:
                return name, {'status': 'unavailable', 'error_type': type(exc).__name__}
        statuses = dict(await asyncio.gather(*(check(name, url) for name, url in targets.items())))
        statuses['database'] = await health()
        return {'components': statuses, 'writes_enabled': settings.enable_write_actions, 'rag_enabled': settings.rag_enabled, 'agent_max_steps': settings.agent_max_steps}

    @router.get('/incidents')
    async def list_incidents(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        with sessions() as session:
            incidents = session.scalars(select(Incident).order_by(Incident.created_at.desc()).limit(limit).offset(offset))
            rows = [{k: v for k, v in asdict(i).items() if k not in ('report', 'agent_state')} for i in incidents]
            return {'incidents': rows, 'total': session.scalar(select(func.count()).select_from(Incident))}

    @router.post('/incidents', status_code=201)
    async def create_incident(body: IncidentCreate):
        with sessions() as session:
            incident = Incident(**redact(body.model_dump()))
            session.add(incident)
            session.commit()
            result = asdict(incident)
        agent.audit(result['id'], 'incident_created', {'title': result['title'], 'service': result['service']})
        return detail(result['id'])

    @router.get('/incidents/{incident_id}')
    async def get_incident(incident_id: str):
        return detail(incident_id)

    @router.post('/incidents/{incident_id}/investigate', status_code=202)
    async def investigate(incident_id: str):
        with sessions() as session:
            incident = session.get(Incident, incident_id)
            if not incident:
                raise HTTPException(404, 'Incident not found')
            if incident.status not in ('OPEN', 'FAILED') or incident_id in tasks:
                raise HTTPException(409, 'Incident cannot start an investigation in its current state')
            active = sum(not t.done() for t in tasks.values())
            if active >= settings.agent_max_parallel_incidents:
                raise HTTPException(409, 'Local model is already investigating another incident; retry after it finishes')
            claimed = session.execute(update(Incident).where(Incident.id == incident_id, Incident.status.in_(['OPEN', 'FAILED'])).values(status='INVESTIGATING', updated_at=now()))
            if claimed.rowcount != 1:
                raise HTTPException(409, 'Incident was already claimed')
            session.commit()
        task = asyncio.create_task(agent.investigate(incident_id))
        tasks[incident_id] = task
        task.add_done_callback(lambda completed: tasks.pop(incident_id, None))
        return detail(incident_id)

    @router.post('/incidents/{incident_id}/verify')
    async def verify(incident_id: str):
        try:
            return await service.verify(incident_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @router.post('/actions/{action_id}/approve')
    async def approve(action_id: str):
        try:
            return await service.approve(action_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @router.post('/actions/{action_id}/reject')
    async def reject(action_id: str):
        try:
            return service.reject(action_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @router.get('/topology')
    async def topology():
        return redact(settings.topology())

    @router.get('/overview')
    async def overview():
        try:
            return await overview_service.snapshot()
        except Exception as exc:
            raise HTTPException(503, 'Server overview unavailable: ' + str(redact(str(exc), 300)))

    @router.get('/tools')
    async def tools():
        return {'tools': list((await gateway.registry()).values()), 'writes_enabled': settings.enable_write_actions}

    @router.post('/runbooks/ingest')
    async def ingest():
        if not rag:
            raise HTTPException(409, 'RAG is disabled')
        try:
            return await rag.ingest_runbooks()
        except Exception as exc:
            raise HTTPException(503, 'Local runbook indexing failed: ' + str(redact(str(exc), 300)))

    @router.get('/evaluations')
    async def evaluations():
        with sessions() as session:
            return {'evaluations': [asdict(run) for run in session.scalars(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(20))]}

    app.include_router(router)
    return app


app = create_app()
