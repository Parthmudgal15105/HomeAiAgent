"""Concise, deterministic findings from observed values; never a second LLM call."""
import re

from .safety import redact


def summarize_observation(tool: str, arguments: dict, envelope: dict) -> str:
    if not envelope.get('ok'):
        return 'Diagnostic could not complete: ' + str(redact(envelope.get('error', 'Unknown execution failure'), 300)) + '. This does not establish target failure.'
    result = envelope.get('result', {})
    if not isinstance(result, dict):
        return f'{tool}: result recorded.'
    if tool == 'http_check':
        target = arguments.get('url', result.get('url', 'configured endpoint'))
        if result.get('reachable'):
            return f"{target} responded with HTTP {result.get('status_code', 'unknown')} in {result.get('latency_ms', '?')} ms."
        return f"{target} did not respond: {redact(result.get('error', 'Connection unavailable'), 250)}."
    if tool == 'docker_inspect':
        state = result.get('state', 'unknown')
        state = state.get('status', 'unknown') if isinstance(state, dict) else state
        return f"{arguments.get('container', result.get('name', 'Container'))}: {state}; health {result.get('health') or 'not configured'}; restart count {result.get('restart_count', '?')}."
    if tool == 'docker_list':
        containers = result.get('containers', [])
        unhealthy = [f"{item.get('name', '?')} ({item.get('state', 'unknown')})" for item in containers if item.get('state') != 'running']
        missing = result.get('missing_configured_containers', [])
        summary = f'{len(containers)} configured containers observed.'
        summary += ' Not running: ' + ', '.join(unhealthy[:8]) + '.' if unhealthy else ' All observed containers report running.'
        if missing:
            summary += ' Missing: ' + ', '.join(missing[:8]) + '.'
        return summary
    if tool in ('service_status', 'cloudflared_status'):
        return f"{arguments.get('service', result.get('service', 'cloudflared'))}: {result.get('state', 'unknown')} ({result.get('substate', result.get('sub_state', 'substate unavailable'))})."
    if tool in ('disk_usage', 'memory_usage'):
        rows = result.get('filesystems', result.get('disks', [result]))
        return '; '.join(f"{row.get('path', row.get('mountpoint', 'Memory' if tool == 'memory_usage' else 'Filesystem'))}: {row.get('used_percent', row.get('percent', '?'))}% used ({row.get('severity', 'severity unavailable')})" for row in rows[:5]) + '.'
    if tool in ('docker_logs', 'journal_logs'):
        lines = result.get('lines') or [entry.get('message', '') for entry in result.get('entries', [])] or str(result.get('output', '')).splitlines()
        matches = [str(line) for line in lines if re.search(r'error|fail|unavailable|refused|denied|timeout|timed out|fatal|rf.?kill', str(line), re.I)]
        if matches:
            return f'{len(lines)} log entries recorded. Error excerpt: {redact(matches[-1], 350)}'
        return f'{len(lines)} log entries recorded; no common error keywords found in this bounded sample.'
    if tool == 'dns_lookup':
        host = arguments.get('hostname', result.get('hostname', 'Configured hostname'))
        return f"{host} resolved to {', '.join(map(str, result.get('addresses', [])[:5]))}." if result.get('resolved') else f'{host} did not resolve.'
    if tool == 'port_check':
        return f"TCP {arguments.get('host', '?')}:{arguments.get('port', '?')} is {'open' if result.get('open') else 'unreachable'} from the host."
    if tool == 'ping_host':
        return f"{arguments.get('hostname', arguments.get('host', 'Configured host'))}: ICMP {'reply received' if result.get('reachable') else 'no reply'}; packet loss {result.get('packet_loss_percent', '?')}%. ICMP blocking is possible."
    if tool == 'network_interfaces':
        return 'Interfaces: ' + ', '.join(f"{item.get('name')}: {item.get('state', 'unknown')}" for item in result.get('interfaces', [])[:10]) + '.'
    if tool == 'system_uptime':
        seconds = result.get('uptime_seconds')
        return f'Host uptime: {round(seconds / 3600, 1)} hours.' if isinstance(seconds, (int, float)) else 'Host uptime recorded.'
    if tool == 'route_table':
        return f"{len(result.get('routes', []))} host routes recorded."
    if tool == 'process_list':
        return f"{len(result.get('processes', []))} processes recorded with executable arguments omitted."
    if tool == 'tailscale_status':
        return f"Tailscale state: {result.get('backend_state', result.get('state', 'unknown'))}; {len(result.get('peers', []))} peers recorded."
    return f'{tool}: structured result recorded.'
