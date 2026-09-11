"""Bounded read-only health snapshot. The independent LLM investigator stays dynamic."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import time

from .gateway import validate_tool
from .safety import redact
from .service import matches


def classify(signals: dict, application_checks: list[dict]) -> tuple[str, list[dict]]:
    findings: list[dict] = []

    def add(level: str, signal: str, message: str):
        findings.append({'level': level, 'signal': signal, 'message': message})

    for key, envelope in signals.items():
        if not envelope.get('ok'):
            add('Warning', key, 'Check unavailable; this signal is unknown, not proof of a target outage.')
            continue
        result = envelope.get('result', {})
        if key.startswith(('disk_usage', 'memory_usage')):
            percent = result.get('used_percent')
            if isinstance(percent, (int, float)) and percent >= 80:
                add('Critical' if percent > 95 else 'Warning', key, f'{percent}% used.')
        elif key == 'system_uptime':
            load = result.get('load_average', [0])[0]
            cores = result.get('cpu_count') or 1
            if load > cores:
                add('Warning', key, f'One-minute load {load} exceeds {cores} logical CPUs; investigate sustained pressure.')
        elif key == 'docker_list':
            for item in result.get('containers', []):
                if item.get('state') != 'running' or 'unhealthy' in str(item.get('status', '')):
                    add('Warning', key, f"{item.get('name')}: {item.get('status', item.get('state'))}. Confirm whether this state is expected.")
            if result.get('missing_configured_containers'):
                add('Warning', key, 'Some configured containers were not found.')
            if result.get('truncated'):
                add('Warning', key, 'Container inventory exceeded the output limit; unobserved containers have unknown status.')
        elif key.startswith('service_status_') or key == 'cloudflared_status':
            if result.get('state') != 'active':
                add('Critical', key, f"Configured system service is {result.get('state', 'unknown')}.")
        elif key == 'tailscale_status':
            if result.get('backend_state') != 'Running':
                add('Critical', key, 'Tailscale is not in Running state.')
            elif result.get('health'):
                add('Warning', key, 'Tailscale reports health messages; inspect the details.')
        elif key == 'network_interfaces':
            usable = [i for i in result.get('interfaces', []) if i.get('name') != 'lo' and i.get('state') == 'UP' and i.get('addresses')]
            if not usable:
                add('Critical', key, 'No active addressed non-loopback interface was observed.')
    for check in application_checks:
        envelope = signals[check['signal']]
        if envelope.get('ok') and not matches(envelope.get('result', {}), check['expect']):
            add('Critical', check['signal'], f"{check['name']}: configured application health check failed.")
    health = 'Critical' if any(f['level'] == 'Critical' for f in findings) else 'Warning' if findings else 'Healthy'
    if not findings:
        add('Healthy', 'snapshot', 'All sampled checks passed. This snapshot does not establish application correctness or historical uptime.')
    return health, findings


class Overview:
    def __init__(self, settings, gateway):
        self.settings, self.gateway = settings, gateway
        self._lock = asyncio.Lock()
        self._cached = None
        self._expires = 0.0

    async def snapshot(self) -> dict:
        async with self._lock:
            if self._cached is not None and time.monotonic() < self._expires:
                return deepcopy(self._cached)
            registry = await self.gateway.registry()
            topology = self.settings.topology()
            plan = [('memory_usage', 'memory_usage', {}), ('system_uptime', 'system_uptime', {}),
                    ('disk_usage', 'disk_usage', {'path': '/'}), ('docker_list', 'docker_list', {}),
                    ('network_interfaces', 'network_interfaces', {})]
            for name in ('tailscale_status', 'cloudflared_status'):
                if name in registry:
                    plan.append((name, name, {}))
            disk_paths = registry.get('disk_usage', {}).get('parameters', {}).get('properties', {}).get('path', {}).get('enum', [])
            if '/storage' in disk_paths:
                plan.append(('disk_usage_storage', 'disk_usage', {'path': '/storage'}))
            systemd = registry.get('service_status', {}).get('parameters', {}).get('properties', {}).get('service', {}).get('enum', [])
            for name in ('docker', 'ssh'):
                if name in systemd:
                    plan.append(('service_status_' + name, 'service_status', {'service': name}))
            checks = []
            for key, profile in topology['services'].items():
                if not profile.get('overview'):
                    continue
                # At most two declared checks per application and six in total.
                for index, check in enumerate(profile.get('health_checks', [])[:2]):
                    if len(checks) >= 6:
                        break
                    signal = f'application_{key}_{index}'
                    plan.append((signal, check['tool'], check['arguments']))
                    checks.append({'signal': signal, 'name': profile.get('name', key), 'expect': check['expect']})
            semaphore = asyncio.Semaphore(3)

            async def collect(key, tool, arguments):
                async with semaphore:
                    try:
                        validate_tool(registry, tool, arguments)
                        result = await asyncio.wait_for(self.gateway.execute(tool, arguments), self.settings.agent_tool_timeout_seconds)
                    except Exception as exc:
                        result = {'ok': False, 'result': {}, 'error': str(redact(str(exc), 300))}
                    return key, {**redact(result), 'tool': tool, 'arguments': arguments}

            signals = dict(await asyncio.gather(*(collect(*item) for item in plan)))
            health, findings = classify(signals, checks)
            self._cached = {'collected_at': datetime.now(timezone.utc).isoformat(), 'health': health,
                            'signals': signals, 'services': topology['services'], 'findings': findings,
                            'cache_seconds': 30, 'scope': 'Bounded current health snapshot; use an investigation for causal diagnosis.'}
            self._expires = time.monotonic() + 30
            return deepcopy(self._cached)
