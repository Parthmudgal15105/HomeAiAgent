"""Deterministic, evidence-based authorization for one autonomous write."""

from datetime import timedelta, timezone

from .gateway import WRITE_TOOLS, validate_tool
from .models import now


def profile_targets(topology: dict, service: str) -> set[str]:
    profiles = topology.get('services', {})
    if service not in profiles:
        return set()
    found, visited = set(), set()

    def visit(name: str):
        if name in visited or name not in profiles:
            return
        visited.add(name)
        profile = profiles[name]
        found.update(profile.get('containers', []))
        found.update(profile.get('systemd_services', []))
        for dependency in profile.get('depends_on', []):
            visit(dependency)

    visit(service)
    return found


def authorize(settings, registry: dict, incident, tool: str, arguments: dict, evidence_ids: list[str]) -> list[str]:
    if not settings.enable_write_actions or not settings.enable_autonomous_actions:
        raise ValueError('Autonomous writes are disabled')
    if tool not in WRITE_TOOLS or tool.startswith('stop_'):
        raise ValueError('INSUFFICIENT_CAPABILITY: autonomous stop or unrestricted write is unavailable')
    metadata = validate_tool(registry, tool, arguments, allow_write=True)
    key = 'container' if tool.endswith('_container') else 'service'
    target = arguments.get(key)
    if target not in metadata.get('autonomous_targets', [target]):
        raise ValueError('Gateway policy requires manual approval for this target and action')
    if target not in profile_targets(settings.topology(), incident.service):
        raise ValueError('Write target is outside this application topology')
    if len(incident.actions) >= settings.autonomous_max_actions_per_incident:
        raise ValueError('Autonomous action budget exhausted for this incident')
    if any(a.arguments.get(key) == target and not a.requires_approval for a in incident.actions):
        raise ValueError('Autonomous target already attempted in this incident; no restart loop')
    evidence = [o for o in incident.observations if o.id in set(evidence_ids)]
    if not evidence or len(evidence) != len(set(evidence_ids)):
        raise ValueError('Current incident evidence IDs are required')
    cutoff = now() - timedelta(minutes=15)
    evidence = [o for o in evidence if (o.created_at.replace(tzinfo=timezone.utc) if o.created_at.tzinfo is None else o.created_at) >= cutoff]
    if not evidence:
        raise ValueError('Fresh observations are required before autonomous write')
    state_tool = 'docker_inspect' if key == 'container' else 'service_status'
    states = [o for o in evidence if o.tool_name == state_tool and o.tool_arguments == {key: target} and o.raw_result.get('ok') is True]
    if not states:
        raise ValueError('A successful exact-target state observation is required before a write')
    state = states[-1].normalized_result
    if key == 'container':
        if target in ('codeduel-api-1', 'codeduel-worker-1'):
            redis_ready = any(o.tool_name == 'docker_inspect' and o.tool_arguments == {'container': 'codeduel-redis-1'}
                              and o.raw_result.get('ok') is True and o.normalized_result.get('state', {}).get('running') is True
                              and o.normalized_result.get('health') == 'healthy' for o in evidence)
            if not redis_ready:
                raise ValueError('Inspect and restore healthy Redis before the API or worker')
        running = state.get('state', {}).get('running')
        unhealthy = state.get('health') == 'unhealthy' or state.get('state', {}).get('restarting') is True
        if tool == 'start_container' and running is not False:
            raise ValueError('Start requires evidence that the container is stopped')
        if tool == 'restart_container' and (running is not True or not unhealthy):
            raise ValueError('Restart requires a running but unhealthy/restarting container')
        if tool == 'restart_container':
            logs = [o for o in evidence if o.tool_name == 'docker_logs' and o.tool_arguments.get('container') == target
                    and o.raw_result.get('ok') is True]
            if not logs:
                raise ValueError('Inspect current target logs before autonomous restart')
            excerpt = '\n'.join(str(line) for line in logs[-1].normalized_result.get('lines', []))[-5000:].lower()
            if any(marker in excerpt for marker in ('mongoserverselectionerror', 'mongodb atlas', 'redis connection refused')):
                raise ValueError('Dependency failure evidence; restarting this container is not justified')
    else:
        active = state.get('state')
        if tool == 'start_service' and active not in ('inactive', 'failed'):
            raise ValueError('Start requires an inactive or failed unit')
        if tool == 'restart_service':
            # A running tunnel is only restarted when origin works but the
            # configured public endpoint fails in this same investigation.
            if target != 'cloudflared' or active != 'active':
                raise ValueError('Active service restart is not authorized for this target/state')
            public_bad = any(o.tool_name == 'http_check' and o.tool_arguments.get('url', '').startswith('https://codeduel.online') and o.normalized_result.get('reachable') is False for o in evidence)
            origin_good = any(o.tool_name == 'http_check' and o.tool_arguments.get('url') in ('http://127.0.0.1:8085', 'http://127.0.0.1:8085/') and o.normalized_result.get('reachable') is True and o.normalized_result.get('status_code') == 200 for o in evidence)
            if not (public_bad and origin_good):
                raise ValueError('Tunnel restart requires failed public and healthy local origin evidence')
    return [o.id for o in evidence]
