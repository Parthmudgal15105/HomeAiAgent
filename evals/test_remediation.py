import pytest

from evals.remediation import RecoverableRedis


@pytest.mark.asyncio
async def test_simulation_requires_approval_and_rejects_replay():
    gateway = RecoverableRedis()
    with pytest.raises(PermissionError):
        await gateway.execute('start_container', {'container': 'redis'})
    approval = {'id': 'mock-action', 'approval_status': 'APPROVED', 'executed_at': 'test-dispatch'}
    assert (await gateway.execute('start_container', {'container': 'redis'}, approval))['result']['simulated']
    assert (await gateway.execute('docker_inspect', {'container': 'redis'}))['result']['state'] == 'running'
    with pytest.raises(PermissionError):
        await gateway.execute('start_container', {'container': 'redis'}, approval)
    assert len(gateway.consumed) == 1


@pytest.mark.asyncio
async def test_simulation_cannot_change_another_target_or_call_unknown_writes():
    gateway = RecoverableRedis()
    approval = {'id': 'mock-action', 'approval_status': 'APPROVED', 'executed_at': 'test-dispatch'}
    with pytest.raises(Exception):
        await gateway.execute('start_container', {'container': 'codeduel-api'}, approval)
    with pytest.raises(PermissionError):
        await gateway.execute('restart_service', {'service': 'docker'}, approval)
    assert not gateway.recovered and not gateway.consumed
