import json

import pytest

from backend.app.overview import Overview, classify
from backend.app.topology import load_topology


def test_new_service_needs_no_agent_code(tmp_path):
    path = tmp_path / 'services.json'
    path.write_text(json.dumps({'services': {'new-app': {'name': 'New workload', 'type': 'web_application', 'public_urls': ['https://example.com'], 'containers': ['new-api'], 'tags': ['application'], 'depends_on': ['queue']}, 'queue': {'type': 'queue'}}}))
    data = load_topology(str(path))
    assert data['services']['new-app']['depends_on'] == ['queue']
    assert data['services']['queue']['name'] == 'queue'


def test_unknown_dependency_and_unknown_profile_fields_fail(tmp_path):
    path = tmp_path / 'services.json'
    for profile in ({'depends_on': ['missing']}, {'shell': 'anything'}):
        path.write_text(json.dumps({'services': {'app': profile}}))
        with pytest.raises(ValueError):
            load_topology(str(path))


def envelope(**result):
    return {'ok': True, 'result': result}


def test_health_never_treats_missing_checks_as_healthy():
    health, findings = classify({'docker_list': {'ok': False, 'error': 'Timeout'}}, [])
    assert health == 'Warning' and 'unknown' in findings[0]['message']
    assert classify({'disk_usage': envelope(used_percent=98)}, [])[0] == 'Critical'
    assert classify({'memory_usage': envelope(used_percent=81)}, [])[0] == 'Warning'
    assert classify({'memory_usage': envelope(used_percent=25)}, [])[0] == 'Healthy'


def test_application_failure_and_expected_stopped_container_are_distinct():
    signals = {'docker_list': envelope(containers=[{'name': 'test', 'state': 'exited'}]), 'app': envelope(status_code=502)}
    assert classify(signals, [])[0] == 'Warning'
    health, _ = classify(signals, [{'signal': 'app', 'name': 'Web app', 'expect': {'status_code': 200}}])
    assert health == 'Critical'


@pytest.mark.asyncio
async def test_overview_caches_and_blocks_write_checks(system):
    settings, _, gateway, _, _, _ = system
    overview = Overview(settings, gateway)
    first = await overview.snapshot()
    count = len(gateway.calls)
    second = await overview.snapshot()
    assert first == second and count == len(gateway.calls)
    assert first['health'] == 'Warning'
    assert all(call[2] is None for call in gateway.calls)


def test_real_topology_is_valid():
    services = load_topology('config/topology.json')['services']
    assert {'codeduel', 'nextcloud', 'jellyfin', 'host'} <= services.keys()
