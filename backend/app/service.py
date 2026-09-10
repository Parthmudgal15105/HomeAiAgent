import asyncio
from datetime import timezone
import json

from sqlalchemy import select, update

from .agent import asdict
from .gateway import validate_tool, WRITE_TOOLS
from .models import Action, Incident, now
from .schemas import CheckSpec
from .safety import redact


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def matches(result: dict, expected: dict) -> bool:
    for path, target in expected.items():
        value = result
        try:
            for key in path.split('.'):
                value = value[int(key)] if isinstance(value, list) else value[key]
        except (KeyError, IndexError, TypeError, ValueError):
            return False
        if value != target or isinstance(target, bool) != isinstance(value, bool):
            return False
    return True


class IncidentService:
    def __init__(self, settings, sessions, agent, gateway, rag=None):
        self.settings, self.sessions, self.agent = settings, sessions, agent
        self.gateway, self.rag = gateway, rag
        self._locks: dict[str, asyncio.Lock] = {}

    async def approve(self, action_id: str) -> dict:
        with self.sessions() as session:
            action = session.get(Action, action_id)
            if not action:
                raise LookupError('Action not found')
            incident_id = action.incident_id
        async with self._locks.setdefault(incident_id, asyncio.Lock()):
            return await self._approve(action_id)

    async def _approve(self, action_id: str) -> dict:
        if not self.settings.enable_write_actions:
            raise ValueError('Write tools are disabled')
        registry = await self.gateway.registry()
        with self.sessions() as session:
            action = session.get(Action, action_id)
            if not action:
                raise LookupError('Action not found')
            if action.approval_status != 'PENDING' or action.executed_at:
                raise ValueError('Action is no longer pending and cannot be replayed')
            if utc(action.expires_at) <= now():
                action.approval_status = 'EXPIRED'
                incident = session.get(Incident, action.incident_id)
                if not any(a.id != action_id and a.approval_status == 'PENDING' for a in incident.actions):
                    incident.status = 'OPEN'
                session.commit()
                raise ValueError('Approval has expired; investigate again before proposing a fresh action')
            incident = session.get(Incident, action.incident_id)
            if incident.status != 'WAITING_FOR_APPROVAL':
                raise ValueError('Incident is not waiting for this approval')
            self.agent.validate_evidence(incident.id, incident.report.get('evidence_observation_ids', []))
            validate_tool(registry, action.tool_name, action.arguments, allow_write=True)
            # Do not change state unless recovery can be checked for BOTH the target
            # and the affected user-facing service using administrator-owned rules.
            for check in self.verification_checks(incident.service, action):
                validate_tool(registry, check.tool, check.arguments)
            # Atomic claim and dispatch marker are durable BEFORE sending a write.
            # An uncertain timeout never causes an automatic retry.
            claimed = session.execute(update(Action).where(Action.id == action_id, Action.approval_status == 'PENDING', Action.executed_at.is_(None)).values(approval_status='APPROVED', approved_at=now(), executed_at=now(), result={'dispatch_status': 'CLAIMED'}))
            if claimed.rowcount != 1:
                session.rollback()
                raise ValueError('Action was already claimed')
            incident.status = 'VERIFYING'
            session.commit()
            session.refresh(action)
            payload = asdict(action)
            incident_id = action.incident_id
        self.agent.audit(incident_id, 'action_approved', {'action_id': action_id, 'tool': payload['tool_name'], 'arguments': payload['arguments'], 'actor': 'authenticated_operator'})
        try:
            result = await asyncio.wait_for(self.gateway.execute(payload['tool_name'], payload['arguments'], approval=payload), timeout=self.settings.agent_write_timeout_seconds)
        except Exception as exc:
            result = {'ok': False, 'error': redact(str(exc), 1000), 'outcome': 'UNKNOWN_REQUIRES_INSPECTION', 'result': {}}
        with self.sessions() as session:
            action = session.get(Action, action_id)
            action.result = redact(result)
            if not result.get('ok'):
                action.verification_status = 'FAILED'
                incident = session.get(Incident, incident_id)
                incident.status = 'WAITING_FOR_APPROVAL' if any(a.id != action_id and a.approval_status == 'PENDING' for a in incident.actions) else 'OPEN'
                incident.agent_state = {**incident.agent_state, 'phase': 'REMEDIATION_FAILED', 'message': 'Action failed or response was uncertain. Inspect before requesting a new action.'}
            session.commit()
        self.agent.audit(incident_id, 'action_executed', {'action_id': action_id, 'result': result})
        if result.get('ok'):
            # Allow ordinary process startup; bounded and read-only afterwards.
            await asyncio.sleep(2)
            await self._verify(incident_id, action_id)
        with self.sessions() as session:
            return asdict(session.get(Action, action_id))

    def reject(self, action_id: str) -> dict:
        with self.sessions() as session:
            action = session.get(Action, action_id)
            if not action:
                raise LookupError('Action not found')
            if action.approval_status != 'PENDING':
                raise ValueError('Only a pending action can be rejected')
            action.approval_status = 'REJECTED'
            incident = session.get(Incident, action.incident_id)
            if incident.status not in ('VERIFYING', 'INVESTIGATING') and not any(a.id != action_id and a.approval_status == 'PENDING' for a in incident.actions):
                incident.status = 'OPEN'
            session.commit()
            result = asdict(action)
        self.agent.audit(result['incident_id'], 'action_rejected', {'action_id': action_id, 'actor': 'authenticated_operator'})
        return result

    def verification_checks(self, service: str, action: Action | None = None) -> list[CheckSpec]:
        services = self.settings.topology().get('services', {})
        if service not in services:
            raise ValueError('No configured service profile; recovery cannot be verified')
        profile = services[service]
        if not profile.get('health_checks'):
            raise ValueError('Affected service has no configured health checks; recovery cannot be verified')
        visited: set[str] = set()
        checks: list[CheckSpec] = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            item = services.get(name, {})
            for dependency in item.get('depends_on', []):
                visit(dependency)
            for check in item.get('health_checks', []):
                checks.append(CheckSpec.model_validate(check))

        visit(service)
        if action:
            target_key = 'container' if action.tool_name in ('restart_container', 'start_container') else 'service'
            target = action.arguments.get(target_key)
            # The administrator's topology must cover the action target as well as the affected service.
            if not any(c.arguments.get(target_key) == target and c.tool in ('docker_inspect', 'service_status') for c in checks):
                raise ValueError('No configured health check verifies the remediation target')
        unique = {}
        for check in checks:
            unique[json.dumps(check.model_dump(), sort_keys=True)] = check
        return list(unique.values())

    async def verify(self, incident_id: str, action_id: str | None = None) -> dict:
        async with self._locks.setdefault(incident_id, asyncio.Lock()):
            return await self._verify(incident_id, action_id)

    async def _verify(self, incident_id: str, action_id: str | None = None) -> dict:
        registry = await self.gateway.registry()
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            if not incident:
                raise LookupError('Incident not found')
            if incident.status == 'INVESTIGATING':
                raise ValueError('Wait for the current investigation to finish')
            if not incident.report.get('evidence_observation_ids'):
                raise ValueError('An evidence-backed diagnosis is required before recovery verification')
            action = session.get(Action, action_id) if action_id else None
            if action and action.incident_id != incident_id:
                raise ValueError('Action does not belong to this incident')
            try:
                checks = self.verification_checks(incident.service, action)
            except ValueError as exc:
                incident.status = 'OPEN'
                incident.agent_state = {**incident.agent_state, 'phase': 'VERIFICATION_BLOCKED', 'verification_error': str(exc)}
                if action:
                    action.verification_status = 'BLOCKED'
                session.commit()
                return {'verified': False, 'error': str(exc), 'checks': []}
            for check in checks:
                validate_tool(registry, check.tool, check.arguments)
            incident.status = 'VERIFYING'
            session.commit()
        results = []
        for check in checks:
            try:
                result = await asyncio.wait_for(self.gateway.execute(check.tool, check.arguments), timeout=self.settings.agent_tool_timeout_seconds)
            except Exception as exc:
                result = {'ok': False, 'result': {}, 'error': redact(str(exc), 1000)}
            passed = result.get('ok') is True and matches(result.get('result', {}), check.expect)
            observation_id = self.agent.record_observation(incident_id, check.tool, check.arguments, result, 'Administrator-configured recovery check ' + ('passed.' if passed else 'failed.'), phase='VERIFICATION')
            results.append({'tool': check.tool, 'arguments': check.arguments, 'expect': check.expect, 'passed': passed, 'observation_id': observation_id})
        verified = bool(results) and all(result['passed'] for result in results)
        with self.sessions() as session:
            incident = session.get(Incident, incident_id)
            pending = [a for a in incident.actions if a.approval_status == 'PENDING']
            incident.status = 'RESOLVED' if verified else ('WAITING_FOR_APPROVAL' if pending else 'OPEN')
            incident.resolved_at = now() if verified else None
            incident.agent_state = {**incident.agent_state, 'phase': 'RESOLVED' if verified else 'VERIFICATION_FAILED', 'verification': results}
            if action_id:
                session.get(Action, action_id).verification_status = 'PASSED' if verified else 'FAILED'
            if verified:
                # Recovery makes any remaining proposals stale; they must never execute later.
                for item in pending:
                    item.approval_status = 'EXPIRED'
            text = f'Service: {incident.service}\nSymptom: {incident.title}\n{incident.description}\nRoot cause: {incident.root_cause}\nSummary: {incident.summary}\nResolution: verified by {json.dumps(results)}'
            if verified:
                text += '\nImportant observations: ' + json.dumps([{'tool': o.tool_name, 'arguments': o.tool_arguments, 'result': o.normalized_result} for o in incident.observations if o.id in incident.report.get('evidence_observation_ids', [])])
            session.commit()
        self.agent.audit(incident_id, 'recovery_verification', {'verified': verified, 'checks': results})
        if verified and self.rag and self.settings.rag_enabled:
            try:
                await self.rag.upsert(f'incident:{incident_id}', text, 'incident', {'incident_id': incident_id})
                self.agent.update_state(incident_id, indexed_for_history=True)
            except Exception as exc:
                self.agent.update_state(incident_id, indexed_for_history=False, indexing_error=redact(str(exc), 300))
        return {'verified': verified, 'checks': results}
