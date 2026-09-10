import asyncio
from datetime import timedelta
import json
import logging
import time

from sqlalchemy import select

from .config import Settings
from .context import compact_context
from .gateway import validate_tool, WRITE_TOOLS
from .models import Action, AuditEvent, Hypothesis, Incident, Observation, now
from .observations import summarize_observation
from .safety import disk_severity, redact, evidence_confidence
from .schemas import Decision

logger = logging.getLogger('homeai.agent')


def asdict(model) -> dict:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


def signature(tool: str, arguments: dict) -> str:
    return tool + ':' + json.dumps(arguments, sort_keys=True, separators=(',', ':'))


class Agent:
    """The production bounded loop; evaluation injects only provider and gateway adapters."""

    def __init__(self, settings: Settings, sessions, gateway, llm, rag=None):
        self.settings, self.sessions = settings, sessions
        self.gateway, self.llm, self.rag = gateway, llm, rag
        self.semaphore = asyncio.Semaphore(settings.agent_max_parallel_incidents)

    def audit(self, incident_id: str, event_type: str, payload: dict):
        safe = redact(payload)
        with self.sessions() as session:
            session.add(AuditEvent(incident_id=incident_id, event_type=event_type, payload=safe))
            session.commit()
        logger.info('%s', json.dumps({'incident_id': incident_id, 'event': event_type, **safe}, default=str))

    def update_state(self, incident_id: str, **updates):
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            incident.agent_state = {**incident.agent_state, **redact(updates)}
            incident.updated_at = now()
            session.commit()

    def context(self, incident_id: str, registry: dict, feedback: str = '') -> dict:
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            observations = [{
                'id': o.id, 'step_number': o.step_number, 'tool_name': o.tool_name,
                'tool_arguments': o.tool_arguments, 'result': o.normalized_result,
                'ok': o.raw_result.get('ok', False), 'interpretation': o.interpretation,
            } for o in incident.observations]
            hypotheses = [{k: v for k, v in asdict(h).items() if k not in ('created_at', 'updated_at', 'incident_id')} for h in incident.hypotheses]
            context = {
                'incident': {'id': incident.id, 'title': incident.title, 'description': incident.description, 'service': incident.service},
                'observations': observations, 'hypotheses': hypotheses,
                'tools': list(registry.values()), 'topology': self.settings.topology(),
                'retrieved_incidents': incident.agent_state.get('retrieved_incidents', []),
                'retrieved_runbooks': incident.agent_state.get('retrieved_runbooks', []),
                'validation_feedback': feedback,
                'remaining_steps': incident.agent_state.get('remaining_steps'),
            }
        return compact_context(redact(context, 2000), self.settings.agent_context_chars)

    def record_observation(self, incident_id: str, tool: str, arguments: dict, result: dict, reason: str = '', phase: str = 'INVESTIGATION') -> str:
        result = redact(result)
        normalized = result.get('result', {})
        if not isinstance(normalized, dict):
            normalized = {'data': normalized}
        if tool == 'disk_usage':
            normalized = dict(normalized)
            percent = normalized.get('used_percent', normalized.get('percent'))
            if isinstance(percent, (int, float)):
                normalized['severity'] = disk_severity(percent, self.settings.disk_warning_percent, self.settings.disk_high_percent, self.settings.disk_critical_percent)
            for entry in normalized.get('filesystems', normalized.get('disks', [])):
                percent = entry.get('percent', entry.get('used_percent'))
                if isinstance(percent, (int, float)):
                    entry['severity'] = disk_severity(percent, self.settings.disk_warning_percent, self.settings.disk_high_percent, self.settings.disk_critical_percent)
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            observation = Observation(incident_id=incident_id, step_number=len(incident.observations) + 1,
                                      tool_name=tool, tool_arguments=redact(arguments), raw_result=result,
                                      normalized_result=normalized,
                                      interpretation=redact(summarize_observation(tool, arguments, {**result, 'result': normalized}) + (' ' + reason if phase == 'VERIFICATION' else ''), 2000),
                                      duration_ms=result.get('duration_ms', 0), phase=phase)
            session.add(observation)
            incident.updated_at = now()
            session.commit()
            return observation.id

    def update_hypotheses(self, incident_id: str, updates):
        if not updates:
            return
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            ids = {o.id for o in incident.observations}
            for update in updates:
                linked = set(update.supporting_observation_ids + update.contradicting_observation_ids)
                if not linked <= ids:
                    raise ValueError('Hypothesis references observations outside this incident')
                if update.status in ('SUPPORTED', 'CONFIRMED') and not update.supporting_observation_ids:
                    raise ValueError('Supported hypotheses require supporting observation IDs')
                if update.status == 'ELIMINATED' and not update.contradicting_observation_ids:
                    raise ValueError('Eliminated hypotheses require contradicting observation IDs')
                existing = next((h for h in incident.hypotheses if h.description.casefold() == update.description.casefold()), None)
                data = redact(update.model_dump())
                supporting = [o for o in incident.observations if o.id in update.supporting_observation_ids]
                data['confidence'], _ = evidence_confidence(supporting, update.confidence, update.contradicting_observation_ids)
                if update.status == 'ELIMINATED':
                    data['confidence'] = min(data['confidence'], .1)
                if existing:
                    for key, value in data.items():
                        setattr(existing, key, value)
                else:
                    session.add(Hypothesis(incident_id=incident_id, **data))
            session.commit()

    def validate_evidence(self, incident_id: str, ids: list[str]) -> list[Observation]:
        if not ids:
            raise ValueError('Diagnosis requires current observations')
        with self.sessions() as session:
            observations = list(session.scalars(select(Observation).where(Observation.incident_id == incident_id, Observation.id.in_(set(ids)))))
        if len(observations) != len(set(ids)):
            raise ValueError('Diagnosis cites nonexistent or unrelated observation IDs')
        if not any(o.raw_result.get('ok') is True for o in observations):
            raise ValueError('Failed tool transports alone cannot establish a root cause')
        return observations

    def propose_action(self, incident_id: str, tool: str, arguments: dict, reason: str, registry: dict) -> str:
        if not self.settings.enable_write_actions:
            raise ValueError('Remediation tools are disabled in this deployment')
        validate_tool(registry, tool, arguments, allow_write=True)
        if tool not in WRITE_TOOLS:
            raise ValueError('Only low-risk write tools can become approval actions')
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            if not incident.report.get('evidence_observation_ids'):
                raise ValueError('An evidence-backed diagnosis is required before proposing writes')
            existing = next((a for a in incident.actions if a.tool_name == tool and a.arguments == arguments and a.approval_status == 'PENDING'), None)
            if existing:
                return existing.id
            action = Action(incident_id=incident_id, tool_name=tool, arguments=arguments, reason=redact(reason), expires_at=now() + timedelta(seconds=self.settings.approval_ttl_seconds))
            session.add(action)
            incident.status = 'WAITING_FOR_APPROVAL'
            session.commit()
            return action.id

    def save_diagnosis(self, incident_id: str, decision: Decision, registry: dict):
        evidence = self.validate_evidence(incident_id, decision.evidence_observation_ids)
        report = redact(decision.model_dump())
        with self.sessions() as session:
            hypotheses = session.get(Incident, incident_id).hypotheses
            contradictions = [oid for h in hypotheses if h.status != 'ELIMINATED' and set(h.supporting_observation_ids) & set(decision.evidence_observation_ids) for oid in h.contradicting_observation_ids]
        confidence, guidance = evidence_confidence(evidence, decision.confidence, contradictions)
        report.update({'confidence': confidence, 'confidence_guidance': guidance, 'confidence_note': 'Evidence-based conservative ceiling, not a calibrated probability. Repeated diagnostics and historical matches do not raise confidence.', 'evidence_validation': 'Citation ownership and tool execution checked; causal interpretation remains model-generated.'})
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            incident.root_cause, incident.root_cause_confidence = redact(decision.root_cause), confidence
            incident.summary, incident.report, incident.status = redact(decision.summary), report, 'OPEN'
            incident.agent_state = {**incident.agent_state, 'phase': 'DIAGNOSED', 'next_action': None}
            session.commit()
        action_errors = []
        for remediation in decision.remediation:
            try:
                self.propose_action(incident_id, remediation.tool, remediation.arguments, remediation.reason, registry)
            except ValueError as exc:
                action_errors.append({'tool': remediation.tool, 'message': str(exc)})
        if action_errors:
            self.update_state(incident_id, remediation_not_executable=action_errors)
        self.audit(incident_id, 'diagnosis', {'root_cause': decision.root_cause, 'confidence': confidence, 'evidence_ids': decision.evidence_observation_ids})

    async def investigate(self, incident_id: str):
        async with self.semaphore:
            started = time.monotonic()
            with self.sessions() as session:
                incident = session.get(Incident, incident_id)
                if not incident:
                    return
                if incident.status in ('RESOLVED', 'VERIFYING', 'WAITING_FOR_APPROVAL'):
                    return
                incident.status = 'INVESTIGATING'
                incident.agent_state = {**incident.agent_state, 'phase': 'STARTING', 'started_at': now().isoformat(), 'remaining_steps': self.settings.agent_max_steps}
                session.commit()
            try:
                await asyncio.wait_for(self._run(incident_id), timeout=self.settings.agent_max_runtime_seconds)
            except Exception as exc:
                message = 'Investigation runtime limit reached' if isinstance(exc, asyncio.TimeoutError) else str(redact(str(exc), 1500))
                with self.sessions() as session:
                    incident = session.get(Incident, incident_id)
                    incident.status = 'FAILED'
                    incident.summary = message
                    incident.agent_state = {**incident.agent_state, 'phase': 'FAILED', 'error': message}
                    session.commit()
                self.audit(incident_id, 'investigation_failed', {'error': message, 'error_type': type(exc).__name__})
            finally:
                provider = getattr(self.llm, 'provider', self.llm)
                self.update_state(incident_id, llm_metrics=getattr(provider, 'metrics', {}), runtime_seconds=round(time.monotonic() - started, 3), finished_at=now().isoformat())

    async def _run(self, incident_id: str):
        registry = await self.gateway.registry()
        registry = {k: v for k, v in registry.items() if k not in WRITE_TOOLS or self.settings.enable_write_actions}
        if self.rag and self.settings.rag_enabled:
            try:
                with self.sessions() as session:
                    incident = session.get(Incident, incident_id)
                    query = f'{incident.service}: {incident.title}. {incident.description}'
                found = await asyncio.wait_for(self.rag.retrieve(query), timeout=min(60, self.settings.agent_llm_timeout_seconds))
                self.update_state(incident_id, retrieved_incidents=[x for x in found if x.get('kind') == 'incident'], retrieved_runbooks=[x for x in found if x.get('kind') == 'runbook'], rag_status='READY')
            except Exception as exc:
                self.update_state(incident_id, rag_status='UNAVAILABLE', rag_error=redact(str(exc), 300))
                self.audit(incident_id, 'rag_unavailable', {'error_type': type(exc).__name__})
        calls: set[str] = set()
        feedback = ''
        invalid_count = 0
        for step in range(self.settings.agent_max_steps):
            self.update_state(incident_id, phase='REASONING', step=step + 1, remaining_steps=self.settings.agent_max_steps - step)
            context = self.context(incident_id, registry, feedback)
            llm_started = time.monotonic()
            decision = await asyncio.wait_for(self.llm.decide_next_action(context), timeout=self.settings.agent_llm_timeout_seconds * 2)
            if not isinstance(decision, Decision):
                decision = Decision.model_validate(decision)
            self.audit(incident_id, 'model_decision', {'step': step + 1, 'latency_ms': round((time.monotonic() - llm_started) * 1000), 'decision': decision.model_dump()})
            try:
                self.update_hypotheses(incident_id, decision.hypothesis_updates)
                if decision.decision_type == 'TOOL_CALL':
                    validate_tool(registry, decision.tool, decision.arguments)
                    call = signature(decision.tool, decision.arguments)
                    if call in calls:
                        raise ValueError('Duplicate diagnostic rejected. Choose a different discriminating check or diagnose with existing evidence.')
                    calls.add(call)
                    self.update_state(incident_id, phase='DIAGNOSTIC', next_action={'tool': decision.tool, 'arguments': decision.arguments, 'reason': decision.reason})
                    tool_started = time.monotonic()
                    try:
                        result = await asyncio.wait_for(self.gateway.execute(decision.tool, decision.arguments), timeout=self.settings.agent_tool_timeout_seconds)
                    except Exception as exc:
                        result = {'tool': decision.tool, 'ok': False, 'result': {}, 'error': redact(str(exc), 1000)}
                    result['duration_ms'] = round((time.monotonic() - tool_started) * 1000, 1)
                    observation_id = self.record_observation(incident_id, decision.tool, decision.arguments, result, decision.reason)
                    self.audit(incident_id, 'tool_result', {'step': step + 1, 'tool': decision.tool, 'ok': result.get('ok'), 'duration_ms': result['duration_ms'], 'observation_id': observation_id})
                    feedback = ''
                elif decision.decision_type == 'DIAGNOSIS':
                    self.save_diagnosis(incident_id, decision, registry)
                    return
                elif decision.decision_type == 'REQUEST_APPROVAL':
                    self.propose_action(incident_id, decision.tool, decision.arguments, decision.reason, registry)
                    self.update_state(incident_id, phase='WAITING_FOR_APPROVAL')
                    return
                else:
                    with self.sessions() as session:
                        incident = session.get(Incident, incident_id)
                        incident.status = 'OPEN'
                        incident.summary = redact(decision.summary or decision.reason or 'Additional operator input is needed.')
                        incident.agent_state = {**incident.agent_state, 'phase': decision.decision_type, 'next_action': None}
                        session.commit()
                    return
            except Exception as exc:
                # Policy/JSON-schema errors are shown to the model, never executed as code.
                from jsonschema.exceptions import ValidationError as SchemaError
                if not isinstance(exc, (ValueError, SchemaError)):
                    raise
                invalid_count += 1
                feedback = str(redact(str(exc), 1000))
                self.audit(incident_id, 'decision_rejected', {'step': step + 1, 'error': feedback, 'tool': decision.tool})
                self.update_state(incident_id, validation_failures=invalid_count, validation_feedback=feedback)
                if invalid_count >= 3:
                    raise ValueError('Investigation stopped after three rejected decisions: ' + feedback) from exc
        raise ValueError('Maximum agent decision steps reached without sufficient evidence')
