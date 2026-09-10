const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { NextRequest } = require('next/server');
const session = require('../.test-build/lib/session.js');
const routes = require('../.test-build/app/api/session/route.js');
const proxy = require('../.test-build/app/api/operator/[...path]/route.js');
const originalEnv = { ...process.env };
const originalFetch = global.fetch;
const origin = 'http://localhost:3080';
function req(method, path = '/api/session', body, cookie, requestOrigin = origin) {
  const headers = { 'content-type': 'application/json' };
  if (requestOrigin !== null) headers.origin = requestOrigin;
  if (cookie) headers.cookie = cookie;
  return new NextRequest(origin + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
}
beforeEach(() => {
  process.env.SESSION_SECRET = 'unit-test-session-secret-only'; // secret-scan: fixture
  process.env.AIOPS_ADMIN_PASSWORD = 'unit-test-login-value-only'; // secret-scan: fixture
  process.env.AIOPS_API_TOKEN = 'unit-test-backend-value-only'; // secret-scan: fixture
  process.env.APP_ORIGIN = origin;
});
afterEach(() => { process.env = { ...originalEnv }; global.fetch = originalFetch; });
test('signed sessions expire at the exact boundary and reject tampering', () => {
  const now = 1800000000000;
  const token = session.createSession('test-secret', now);
  assert.equal(session.validSession(token, 'test-secret', now), true);
  assert.equal(session.validSession(token, 'wrong', now), false);
  assert.equal(session.validSession(token + '.extra', 'test-secret', now), false);
  assert.equal(session.validSession(token.replace(/^\d/, '9'), 'test-secret', now), false);
  assert.equal(session.validSession(token, 'test-secret', now + session.SESSION_LIFETIME_MS), false);
  assert.equal(session.validSession('NaN.invalid', 'test-secret', now), false);
  assert.equal(session.validSession(undefined, 'test-secret', now), false);
});
test('login rejects invalid credentials and requires configured authentication', async () => {
  assert.equal((await routes.POST(req('POST', undefined, { password: 'wrong' }))).status, 401);
  delete process.env.SESSION_SECRET;
  assert.equal((await routes.POST(req('POST', undefined, { password: 'unit-test-login-value-only' }))).status, 503); // secret-scan: fixture
});
test('valid login sets private cookie; authenticated check and logout work', async () => {
  const response = await routes.POST(req('POST', undefined, { password: 'unit-test-login-value-only' })); // secret-scan: fixture
  assert.equal(response.status, 200);
  const cookie = response.headers.get('set-cookie');
  assert.match(cookie, /HttpOnly/i);
  assert.match(cookie, /SameSite=strict/i);
  assert.match(cookie, /Max-Age=28800/i);
  assert.equal((await (await routes.GET(req('GET', undefined, undefined, cookie))).json()).authenticated, true);
  const logout = await routes.DELETE(req('DELETE', undefined, undefined, cookie));
  assert.equal(logout.status, 200);
  assert.match(logout.headers.get('set-cookie'), /Max-Age=0/i);
  assert.equal((await (await routes.GET(req('GET'))).json()).authenticated, false);
});
test('login and logout reject missing or foreign origins', async () => {
  for (const badOrigin of [null, 'https://attacker.example']) {
    assert.equal((await routes.POST(req('POST', undefined, {}, undefined, badOrigin))).status, 403);
    assert.equal((await routes.DELETE(req('DELETE', undefined, undefined, undefined, badOrigin))).status, 403);
  }
});
test('API proxy rejects unauthenticated, expired, foreign-origin, and unregistered calls', async () => {
  const ctx = { params: Promise.resolve({ path: ['overview'] }) };
  assert.equal((await proxy.GET(req('GET'), ctx)).status, 401);
  const expired = 'aiops_session=' + session.createSession(process.env.SESSION_SECRET, Date.now() - session.SESSION_LIFETIME_MS - 1);
  assert.equal((await proxy.GET(req('GET', undefined, undefined, expired), ctx)).status, 401);
  const cookie = 'aiops_session=' + session.createSession(process.env.SESSION_SECRET);
  assert.equal((await proxy.POST(req('POST', undefined, {}, cookie, 'https://attacker.example'), ctx)).status, 403);
  assert.equal((await proxy.GET(req('GET', undefined, undefined, cookie), { params: Promise.resolve({ path: ['arbitrary-command'] }) })).status, 404);
});
test('authenticated overview forwards only the server-side credential', async () => {
  const cookie = 'aiops_session=' + session.createSession(process.env.SESSION_SECRET);
  let called = false;
  global.fetch = async (url, options) => {
    called = true;
    assert.equal(url, 'http://127.0.0.1:18000/api/overview');
    assert.equal(options.headers.Authorization, 'Bearer unit-test-backend-value-only');
    assert.equal(options.headers.Cookie, undefined);
    return Response.json({ health: 'Healthy' });
  };
  const response = await proxy.GET(req('GET', undefined, undefined, cookie), { params: Promise.resolve({ path: ['overview'] }) });
  assert.equal(response.status, 200);
  assert.equal(called, true);
  assert.equal((await response.json()).health, 'Healthy');
});
