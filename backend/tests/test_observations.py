import pytest

from backend.app.observations import summarize_observation


@pytest.mark.parametrize('tool,args,result,expected', [
    ('http_check', {'url': 'https://example.test'}, {'reachable': True, 'status_code': 502, 'latency_ms': 10}, 'HTTP 502'),
    ('docker_inspect', {'container': 'api'}, {'state': {'status': 'restarting'}, 'health': 'unhealthy', 'restart_count': 42}, 'restart count 42'),
    ('docker_list', {}, {'containers': [{'name': 'api', 'state': 'exited'}, {'name': 'redis', 'state': 'running'}]}, 'api (exited)'),
    ('service_status', {'service': 'cloudflared'}, {'state': 'inactive', 'substate': 'dead'}, 'inactive (dead)'),
    ('disk_usage', {}, {'path': '/', 'used_percent': 97, 'severity': 'critical'}, '97% used (critical)'),
    ('docker_logs', {}, {'lines': ['ready', 'MongoServerSelectionError password=sensitive']}, 'MongoServerSelectionError password=[REDACTED]'),
    ('dns_lookup', {'hostname': 'example.test'}, {'resolved': True, 'addresses': ['192.0.2.1']}, 'resolved to 192.0.2.1'),
])
def test_findings_describe_results(tool, args, result, expected):
    summary = summarize_observation(tool, args, {'ok': True, 'result': result})
    assert expected in summary
    assert 'sensitive' not in summary


def test_execution_failure_does_not_assert_server_failure():
    summary = summarize_observation('docker_list', {}, {'ok': False, 'error': 'Authorization denied'})
    assert 'does not establish target failure' in summary
