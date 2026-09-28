import asyncio
from datetime import timedelta
import json
import logging
import time

from sqlalchemy import select

from .config import Settings
from .context import compact_context
from .failures import FailureKind, model_failure_kind, tool_failure_kind
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
        self.service = None
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

    def record_step_timing(self, incident_id: str, step: int, started: float, *, phase: str, tool: str | None = None):
        """Persist a bounded timing trail without sending raw logs to the model."""
        entry = {
            'step': step,
            'agent_step_time_ms': round((time.monotonic() - started) * 1000, 1),
            'phase': phase,
            **({'tool': tool} if tool else {}),
        }
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            timings = list(incident.agent_state.get('step_timings', []))[-(self.settings.agent_max_steps - 1):]
            timings.append(entry)
            incident.agent_state = {**incident.agent_state, 'step_timings': timings}
            incident.updated_at = now()
            session.commit()

    def context(self, incident_id: str, registry: dict, feedback: str = '') -> dict:
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            observations = [{
                'id': o.id, 'step_number': o.step_number, 'tool_name': o.tool_name,
                'tool_arguments': o.tool_arguments, 'result': o.normalized_result,
                'ok': o.raw_result.get('ok', False), 'interpretation': o.interpretation,
                **({'phase': o.phase} if o.phase == 'REMEDIATION' else {}),
            } for o in incident.observations]
            hypotheses = [{k: v for k, v in asdict(h).items() if k not in ('created_at', 'updated_at', 'incident_id')} for h in incident.hypotheses]
            context = {
                'incident': {'id': incident.id, 'title': incident.title, 'description': incident.description, 'service': incident.service},
                # Stable tool/topology prefix lets Ollama reuse its prompt cache.
                # Putting growing observations first re-evaluated every schema on
                # every CPU step, even though the permitted tools never changed.
                'tools': list(registry.values()), 'topology': self.settings.topology(),
                'retrieved_incidents': incident.agent_state.get('retrieved_incidents', []),
                'retrieved_runbooks': incident.agent_state.get('retrieved_runbooks', []),
                'observations': observations, 'hypotheses': hypotheses,
                'validation_feedback': feedback,
                'remaining_steps': incident.agent_state.get('remaining_steps'),
                'autonomous_actions_enabled': self.settings.enable_write_actions and self.settings.enable_autonomous_actions,
            }
        return compact_context(redact(context, 2000), self.settings.agent_context_chars)

    def record_observation(self, incident_id: str, tool: str, arguments: dict, result: dict, reason: str = '', phase: str = 'INVESTIGATION') -> str:
        result = dict(redact(result))
        if not result.get('ok'):
            result.setdefault('failure_kind', tool_failure_kind(result.get('error')).value)
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

    async def retrieve_rag(self, incident_id: str):
        """Retrieve after initial evidence by default to avoid evicting the CPU model."""
        if not self.rag or not self.settings.rag_enabled:
            return
        started = time.monotonic()
        try:
            with self.sessions() as session:
                incident = session.get(Incident, incident_id)
                query = f'{incident.service}: {incident.title}. {incident.description}'
            found = await asyncio.wait_for(self.rag.retrieve(query), timeout=min(60, self.settings.agent_llm_timeout_seconds))
            self.update_state(
                incident_id,
                retrieved_incidents=[x for x in found if x.get('kind') == 'incident'],
                retrieved_runbooks=[x for x in found if x.get('kind') == 'runbook'],
                rag_status='READY',
                rag_retrieval_time_ms=round((time.monotonic() - started) * 1000, 1),
            )
        except Exception as exc:
            self.update_state(
                incident_id, rag_status='UNAVAILABLE',
                rag_error=redact(str(exc), 300),
                rag_failure_kind=FailureKind.INFRASTRUCTURE_FAILURE.value,
                rag_retrieval_time_ms=round((time.monotonic() - started) * 1000, 1),
            )
            self.audit(incident_id, 'rag_unavailable', {'error_type': type(exc).__name__, 'failure_kind': FailureKind.INFRASTRUCTURE_FAILURE.value})

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

    @staticmethod
    def _container_running(result: dict) -> bool | None:
        state = result.get('state')
        if isinstance(state, dict):
            return state.get('running')
        if isinstance(state, str):
            return state == 'running'
        return None

    def validate_remediation_preconditions(self, incident_id: str, tool: str, arguments: dict) -> None:
        """Require fresh exact-target state evidence before a model proposes a write.

        This is deliberately narrower than autonomous authorization: it does not
        auto-approve a write, but prevents an LLM from proposing a start for a
        running target or a restart for a stopped/healthy one.
        """
        key = 'container' if tool.endswith('_container') else 'service'
        target = arguments.get(key)
        state_tool = 'docker_inspect' if key == 'container' else 'service_status'
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            states = [o for o in incident.observations if o.tool_name == state_tool
                      and o.tool_arguments == {key: target} and o.raw_result.get('ok') is True]
        if not states:
            raise ValueError('A successful exact-target state observation is required before proposing recovery')
        state = states[-1].normalized_result
        if key == 'container':
            running = self._container_running(state)
            details = state.get('state') if isinstance(state.get('state'), dict) else {}
            unhealthy = state.get('health') == 'unhealthy' or bool(details.get('restarting'))
            if tool == 'start_container' and running is not False:
                raise ValueError('Start proposal requires evidence that the container is stopped')
            if tool == 'restart_container' and (running is not True or not unhealthy):
                raise ValueError('Restart proposal requires evidence that the container is running and unhealthy')
        else:
            active = state.get('state')
            if tool == 'start_service' and active not in ('inactive', 'failed'):
                raise ValueError('Start proposal requires inactive or failed service evidence')
            if tool == 'restart_service' and active != 'active':
                raise ValueError('Restart proposal requires active service evidence')

    def propose_action(self, incident_id: str, tool: str, arguments: dict, reason: str, registry: dict) -> str:
        if not self.settings.enable_write_actions:
            raise ValueError('Remediation tools are disabled in this deployment')
        validate_tool(registry, tool, arguments, allow_write=True)
        if tool not in WRITE_TOOLS:
            raise ValueError('Only low-risk write tools can become approval actions')
        self.validate_remediation_preconditions(incident_id, tool, arguments)
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
        for remediation in ([] if self.settings.enable_autonomous_actions else decision.remediation):
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
                runtime_limit = isinstance(exc, asyncio.TimeoutError)
                message = 'Investigation runtime limit reached' if runtime_limit else str(redact(str(exc), 1500)) or type(exc).__name__
                with self.sessions() as session:
                    incident = session.get(Incident, incident_id)
                    prior = incident.agent_state.get('last_failure', {})
                    failure_kind = prior.get('kind') or FailureKind.INFRASTRUCTURE_FAILURE.value
                    incident.status = 'FAILED'
                    incident.summary = message
                    incident.agent_state = {**incident.agent_state, 'phase': 'FAILED', 'error': message,
                                            'failure': {'kind': failure_kind, 'message': message,
                                                        'source': prior.get('source', 'agent_runtime' if runtime_limit else 'agent')}}
                    session.commit()
                self.audit(incident_id, 'investigation_failed', {'error': message, 'error_type': type(exc).__name__, 'failure_kind': failure_kind})
            finally:
                provider = getattr(self.llm, 'provider', self.llm)
                self.update_state(incident_id, llm_metrics=getattr(provider, 'metrics', {}), runtime_seconds=round(time.monotonic() - started, 3), finished_at=now().isoformat())

    async def _run(self, incident_id: str):
        registry = await self.gateway.registry()
        registry = {k: v for k, v in registry.items() if k not in WRITE_TOOLS or self.settings.enable_write_actions}
        calls: set[str] = set()
        feedback = ''
        invalid_count = 0
        max_decisions = min(self.settings.agent_max_steps, self.settings.agent_max_model_calls)
        rag_retrieved = not (self.rag and self.settings.rag_enabled)
        for step in range(max_decisions):
            step_started = time.monotonic()
            if not rag_retrieved:
                with self.sessions() as session:
                    observation_count = len(session.get(Incident, incident_id).observations)
                if observation_count >= self.settings.rag_retrieve_after_observations:
                    await self.retrieve_rag(incident_id)
                    rag_retrieved = True
            self.update_state(incident_id, phase='REASONING', step=step + 1,
                              remaining_steps=max_decisions - step, model_calls=step + 1,
                              model_call_budget=max_decisions)
            context = self.context(incident_id, registry, feedback)
            llm_started = time.monotonic()
            try:
                # The provider has one constrained repair attempt internally;
                # this outer deadline is deliberately the configured decision
                # budget, not an unbounded second timeout window.
                decision = await asyncio.wait_for(self.llm.decide_next_action(context), timeout=self.settings.agent_llm_timeout_seconds)
            except Exception as exc:
                kind = model_failure_kind(exc)
                failure = {'kind': kind.value, 'source': 'model', 'step': step + 1,
                           'message': str(redact(str(exc), 500)) or type(exc).__name__}
                self.update_state(incident_id, phase='MODEL_FAILED', last_failure=failure)
                self.audit(incident_id, 'model_failure', failure)
                self.record_step_timing(incident_id, step + 1, step_started, phase='MODEL_FAILED')
                raise
            if not isinstance(decision, Decision):
                decision = Decision.model_validate(decision)
            self.audit(incident_id, 'model_decision', {'step': step + 1, 'total_model_time_ms': round((time.monotonic() - llm_started) * 1000), 'decision': decision.model_dump()})
            try:
                hypothesis_feedback = ''
                try:
                    self.update_hypotheses(incident_id, decision.hypothesis_updates)
                except ValueError as exc:
                    # Hypothesis metadata cannot authorize a tool. Reject it
                    # independently so a separately valid, read-only decision
                    # can still make progress and receive corrective feedback.
                    hypothesis_feedback = 'Hypothesis update ignored: ' + str(redact(str(exc), 800))
                    self.audit(incident_id, 'hypothesis_update_rejected', {'step': step + 1, 'error': hypothesis_feedback})
                if decision.decision_type == 'TOOL_CALL':
                    validate_tool(registry, decision.tool, decision.arguments)
                    call = signature(decision.tool, decision.arguments)
                    if call in calls:
                        raise ValueError('Duplicate diagnostic rejected. Choose a different discriminating check or diagnose with existing evidence.')
                    calls.add(call)
                    self.update_state(incident_id, phase='DIAGNOSTIC', next_action={'tool': decision.tool, 'arguments': decision.arguments, 'reason': decision.reason})
                    tool_started = time.monotonic()
                    try:
                        timeout = max(30, self.settings.agent_tool_timeout_seconds * 2) if decision.tool == 'check_application_health' else self.settings.agent_tool_timeout_seconds
                        result = await asyncio.wait_for(self.gateway.execute(decision.tool, decision.arguments), timeout=timeout)
                    except Exception as exc:
                        result = {'tool': decision.tool, 'ok': False, 'result': {}, 'error': redact(str(exc), 1000),
                                  'failure_kind': tool_failure_kind(exc).value}
                    result['duration_ms'] = round((time.monotonic() - tool_started) * 1000, 1)
                    result['tool_execution_time_ms'] = result['duration_ms']
                    if not result.get('ok'):
                        result.setdefault('failure_kind', tool_failure_kind(result.get('error')).value)
                    observation_id = self.record_observation(incident_id, decision.tool, decision.arguments, result, decision.reason)
                    self.audit(incident_id, 'tool_result', {
                        'step': step + 1, 'tool': decision.tool, 'ok': result.get('ok'),
                        'tool_execution_time_ms': result['duration_ms'], 'observation_id': observation_id,
                        **({'failure_kind': result['failure_kind']} if not result.get('ok') else {}),
                    })
                    self.record_step_timing(incident_id, step + 1, step_started, phase='DIAGNOSTIC', tool=decision.tool)
                    feedback = hypothesis_feedback
                elif decision.decision_type == 'DIAGNOSIS':
                    self.save_diagnosis(incident_id, decision, registry)
                    self.record_step_timing(incident_id, step + 1, step_started, phase='DIAGNOSED')
                    if self.settings.enable_autonomous_actions and decision.remediation and self.service:
                        remediation = decision.remediation[0]
                        try:
                            await self.service.execute_autonomous(incident_id, remediation.tool, remediation.arguments,
                                                                  remediation.reason, decision.evidence_observation_ids)
                        except ValueError as exc:
                            self.update_state(incident_id, remediation_not_executable=[{'tool': remediation.tool, 'message': str(exc)}])
                            with self.sessions() as session:
                                actions = [a for a in session.get(Incident, incident_id).actions if not a.requires_approval]
                            await self.service.verify(incident_id, actions[-1].id if actions else None)
                            return
                        feedback = 'One targeted action was executed and verified. Inspect its new observations; continue diagnosis if recovery is incomplete.'
                        calls.clear()  # A write makes a repeated diagnostic meaningful.
                        continue
                    if self.settings.enable_autonomous_actions and self.service:
                        with self.sessions() as session:
                            actions = [a for a in session.get(Incident, incident_id).actions if not a.requires_approval]
                        await self.service.verify(incident_id, actions[-1].id if actions else None)
                    return
                elif decision.decision_type == 'EXECUTE_ACTION':
                    if not self.service:
                        raise ValueError('Autonomous executor is unavailable')
                    action = await self.service.execute_autonomous(incident_id, decision.tool, decision.arguments, decision.reason)
                    calls.clear()
                    feedback = ('Action and exact-target verification passed.' if action['verification_status'] == 'PASSED'
                                else 'Action failed or exact-target verification failed. Do not retry this target; inspect current evidence and report unresolved if no new safe action exists.')
                    self.update_state(incident_id, phase='REASONING', next_action=None, last_action_id=action['id'])
                    self.record_step_timing(incident_id, step + 1, step_started, phase='REMEDIATION', tool=decision.tool)
                elif decision.decision_type == 'REQUEST_APPROVAL':
                    self.propose_action(incident_id, decision.tool, decision.arguments, decision.reason, registry)
                    self.update_state(incident_id, phase='WAITING_FOR_APPROVAL')
                    self.record_step_timing(incident_id, step + 1, step_started, phase='WAITING_FOR_APPROVAL', tool=decision.tool)
                    return
                else:
                    with self.sessions() as session:
                        incident = session.get(Incident, incident_id)
                        escalated = decision.decision_type == 'NEED_USER_INPUT'
                        capability_status = decision.capability_status or ('MISSING_TOOL' if decision.capability_gap else 'KNOWN_TOOL')
                        gaps = list(incident.agent_state.get('capability_gaps', []))
                        if decision.capability_gap and decision.capability_gap not in gaps:
                            gaps.append(decision.capability_gap)
                        incident.status = 'ESCALATED' if escalated else 'OPEN'
                        incident.summary = redact(decision.summary or decision.reason or 'Additional operator input is needed.')
                        incident.report = {
                            **incident.report,
                            'status': 'ESCALATED' if escalated else 'OPEN',
                            'reason': redact(decision.reason),
                            'capability_status': capability_status,
                            'capability_gap': decision.capability_gap,
                            'missing_capability': redact(decision.missing_capability),
                            'recommended_next_check': redact(decision.recommended_next_check),
                        }
                        incident.agent_state = {**incident.agent_state, 'phase': 'ESCALATED' if escalated else decision.decision_type,
                                               'next_action': None, 'capability_gaps': gaps}
                        session.commit()
                    self.audit(incident_id, 'incident_escalated' if escalated else 'investigation_stopped', {
                        'capability_status': capability_status,
                        'capability_gap': decision.capability_gap,
                        'missing_capability': decision.missing_capability,
                        'recommended_next_check': decision.recommended_next_check,
                    })
                    self.record_step_timing(incident_id, step + 1, step_started, phase='ESCALATED' if escalated else decision.decision_type)
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
                self.record_step_timing(incident_id, step + 1, step_started, phase='DECISION_REJECTED', tool=decision.tool)
                if invalid_count >= 3:
                    self.update_state(incident_id, loop_detected=True, loop_reason='REJECTED_DECISION_LIMIT',
                                      last_failure={'kind': FailureKind.MODEL_INVALID_OUTPUT.value, 'source': 'model_policy',
                                                    'step': step + 1, 'message': 'Repeated rejected model decisions'})
                    raise ValueError('Investigation stopped after three rejected decisions: ' + feedback) from exc
        exhausted = 'Model decision budget exhausted' if self.settings.agent_max_model_calls < self.settings.agent_max_steps else 'Maximum agent decision steps reached'
        self.update_state(incident_id, loop_detected=True, loop_reason='MODEL_CALL_BUDGET' if 'Model' in exhausted else 'STEP_BUDGET',
                          last_failure={'kind': FailureKind.MODEL_INVALID_OUTPUT.value, 'source': 'model_policy',
                                        'message': exhausted})
        raise ValueError(exhausted + ' without sufficient evidence')
