"""Verify private stack and compare unrelated production health without emitting credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import urllib.request


def assert_gateway_write_policy(tools: list[dict], source_policy: Path = Path('config/gateway.json')) -> None:
    """Ensure the authenticated deployed registry matches the reviewed source policy.

    This prevents a deployment from silently widening manual or autonomous write
    targets.  It intentionally compares metadata returned by the running,
    authenticated gateway; it does not perform any action.
    """
    policy = json.loads(source_policy.read_text())
    expected = {
        action: sorted(target for target, actions in policy.get('allowed_actions', {}).items() if action in actions)
        for action in ('start_container', 'stop_container', 'restart_container',
                       'start_service', 'stop_service', 'restart_service')
    }
    expected = {action: targets for action, targets in expected.items() if targets}
    actual = {tool['name']: tool for tool in tools if tool.get('risk_level') != 'READ_ONLY'}
    assert set(actual) == set(expected), 'Gateway write tools differ from config/gateway.json'
    for action, targets in expected.items():
        metadata = actual[action]
        field = 'container' if action.endswith('_container') else 'service'
        assert sorted(metadata['parameters']['properties'][field].get('enum', [])) == targets, f'{action} targets differ from config/gateway.json'
        autonomous = sorted(target for target, actions in policy.get('autonomous_actions', {}).items() if action in actions)
        assert sorted(metadata.get('autonomous_targets', [])) == autonomous, f'{action} autonomous targets differ from config/gateway.json'


def production():
    results = {}
    for url in ('https://codeduel.online', 'https://codeduel.online/api/explore/problems', 'http://127.0.0.1:8085/healthz'):
        try:
            # Match the existing production baseline probe. The public edge
            # rejects urllib's default user agent even while curl and browsers
            # succeed; that 403 must not silently disable regression checks.
            response = subprocess.run(['curl', '--max-time', '15', '-sS', '-o', '/dev/null', '-w', '%{http_code}', url], capture_output=True, text=True, timeout=20)
            results[url] = int(response.stdout) if response.returncode == 0 else 0
        except Exception:
            results[url] = 0
    rows = subprocess.check_output(['docker', 'ps', '-a', '--filter', 'label=com.docker.compose.project=codeduel', '--format', '{{.Names}}|{{.Status}}'], text=True)
    results['containers'] = {line.split('|', 1)[0]: 'healthy' if '(healthy)' in line else 'unhealthy' for line in rows.splitlines()}
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--production-only', action='store_true')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    state = production()
    if args.production_only:
        print(json.dumps(state, indent=2)); return
    if args.baseline:
        before = json.loads(args.baseline.read_text())
        for key, value in before.items():
            if key == 'containers':
                assert all(state['containers'].get(k) == 'healthy' for k, v in value.items() if v == 'healthy'), 'Existing production container health regressed; stop deployment and inspect'
            elif value == 200:
                assert state[key] == 200, 'Existing production HTTP health regressed; stop deployment and inspect'
    values = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines() if line and not line.startswith('#'))
    request = urllib.request.Request('http://127.0.0.1:18000/api/health', headers={'Authorization': 'Bearer ' + values['AIOPS_API_TOKEN']})
    with urllib.request.urlopen(request, timeout=30) as response:
        health = json.load(response)
    assert all(v['status'] == 'ok' for v in health['components'].values()), 'An internal component is unavailable'
    with urllib.request.urlopen(values['APP_ORIGIN'] + '/api/session', timeout=10) as response:
        assert response.status == 200
    request = urllib.request.Request('http://127.0.0.1:18081/tools', headers={'Authorization': 'Bearer ' + values['GATEWAY_TOKEN']})
    with urllib.request.urlopen(request, timeout=10) as response:
        gateway_tools = json.load(response)['tools']
    assert len(gateway_tools) >= 19
    assert_gateway_write_policy(gateway_tools)
    assert subprocess.run(['systemctl', 'is-active', '--quiet', 'aiops-gateway']).returncode == 0
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    for container in ('aiops-backend-1', 'aiops-frontend-1'):
        deployed = subprocess.check_output(['docker', 'inspect', '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}', container], text=True).strip()
        assert deployed == revision, f'{container} image does not match the checked-out commit'
    result = {'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), 'components': {k: v['status'] for k, v in health['components'].items()}, 'frontend': 'ok', 'gateway_authenticated_registry': 'ok', 'production': state}
    Path('reports/private').mkdir(parents=True, exist_ok=True)
    Path('reports/private/deployment-health.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
