"""Deterministic, bounded application checks from administrator-owned topology."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import time

from .failures import tool_failure_kind
from .gateway import validate_tool
from .safety import redact
from .service import matches


def application_names(topology: dict) -> list[str]:
    return sorted(name for name, profile in topology.get('services', {}).items() if profile.get('health_checks'))


async def check_application_health(settings, gateway, application: str) -> dict:
    services = settings.topology().get('services', {})
    if application not in services or not services[application].get('health_checks'):
        raise ValueError('Application has no configured health checks')
    registry = await gateway.registry()
    names: list[str] = []

    def visit(name: str):
        if name in names:
            return
        names.append(name)
        for dependency in services[name].get('depends_on', []):
            visit(dependency)

    visit(application)
    plan = [(name, check) for name in names for check in services[name].get('health_checks', [])]
    if len(plan) > 24:
        raise ValueError('Application health plan exceeds 24 configured checks')
    semaphore = asyncio.Semaphore(6)

    async def run(name: str, check: dict) -> dict:
        async with semaphore:
            tool, arguments = check['tool'], check['arguments']
            started = time.monotonic()
            try:
                validate_tool(registry, tool, arguments)
                envelope = await asyncio.wait_for(gateway.execute(tool, arguments), settings.agent_tool_timeout_seconds)
            except Exception as exc:
                envelope = {'ok': False, 'result': {}, 'error': str(redact(str(exc), 300)),
                            'failure_kind': tool_failure_kind(exc).value}
            full_result = redact(envelope.get('result', {}), 1000)
            passed = envelope.get('ok') and matches(full_result, check['expect'])
            encoded = json.dumps(full_result, ensure_ascii=False, default=str)
            result = full_result if len(encoded) <= 3000 else {'truncated': True, 'preview': encoded[:2000]}
            return {'component': name, 'tool': tool, 'arguments': arguments, 'expect': check['expect'],
                    'status': 'HEALTHY' if passed else 'UNHEALTHY' if envelope.get('ok') else 'UNKNOWN',
                    'result': result, 'error': redact(envelope.get('error'), 300),
                    'failure_kind': envelope.get('failure_kind'),
                    'tool_execution_time_ms': round((time.monotonic() - started) * 1000, 1)}

    checks = await asyncio.gather(*(run(name, check) for name, check in plan))
    components = []
    for name in names:
        own = [check for check in checks if check['component'] == name]
        status = 'NOT_CHECKED' if not own else 'UNHEALTHY' if any(check['status'] == 'UNHEALTHY' for check in own) else 'UNKNOWN' if any(check['status'] == 'UNKNOWN' for check in own) else 'HEALTHY'
        components.append({'id': name, 'name': services[name].get('name', name), 'status': status, 'checks': own})
    checked = [item for item in components if item['status'] != 'NOT_CHECKED']
    status = 'UNHEALTHY' if any(item['status'] == 'UNHEALTHY' for item in checked) else 'UNKNOWN' if any(item['status'] == 'UNKNOWN' for item in checked) else 'HEALTHY'
    return {'application': application, 'status': status, 'components': components,
            'collected_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Configured read-only checks only; a healthy snapshot does not prove full user-journey correctness.'}
