const { test } = require('node:test');
const assert = require('node:assert/strict');
const { QUICK_ACTIONS, suggestedService, resolutionTime, serviceLabel } = require('../.test-build/lib/dashboard.js');
test('six quick actions select configured services without a fixed application name', () => {
  const services = { machine: { type: 'linux_host' }, shop: { type: 'web_application', name: 'My shop' }, vpn: { tags: ['tailscale'] } };
  assert.equal(QUICK_ACTIONS.length, 6);
  assert.equal(suggestedService('health', services), 'machine');
  assert.equal(suggestedService('application', services), 'shop');
  assert.equal(suggestedService('tailscale', services), 'vpn');
  assert.equal(serviceLabel('shop', services.shop), 'My shop');
});
test('resolution duration uses resolved time, not last activity', () => {
  assert.equal(resolutionTime('2026-09-10T10:00:00Z', '2026-09-10T10:01:30Z'), '1m 30s');
  assert.equal(resolutionTime('2026-09-10T10:00:00Z'), 'Not resolved');
});

test('observation indicators reflect failures inside normalized results', () => {
  const { observationFailed } = require('../.test-build/lib/dashboard.js');
  assert.equal(observationFailed({}, false), true);
  assert.equal(observationFailed({ state: { status: 'exited' } }), true);
  assert.equal(observationFailed({ status_code: 502 }), true);
  assert.equal(observationFailed({ state: { status: 'running' }, health: 'healthy' }), false);
});
