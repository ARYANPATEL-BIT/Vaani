/* global process */
/**
 * authApi.test.js -- the three sign-in calls (authApi.js), tested on the REAL
 * module with a fake fetch passed in. No backend, no network.
 *
 * Covers: the relative path and method of each call, the JSON body of the
 * sign-in POST, status and body handed back, a 204 or non-JSON body (body
 * null), a network failure (status null, never a throw), and the abort
 * signal reaching fetch.
 *
 * Run with:
 *   node frontend/src/api/authApi.test.js
 */

import { fetchMe, signInWithGoogle, logout } from './authApi.js';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${description}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${description}`);
  }
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** A fake fetch that records its call and answers with `status` and `body`. */
function fakeFetch(status, body) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url, options });
    return {
      status,
      json: async () => {
        if (body === undefined) throw new SyntaxError('no JSON body');
        return body;
      },
    };
  };
  fn.calls = calls;
  return fn;
}

const failingFetch = async () => { throw new TypeError('Failed to fetch'); };

console.log('fetchMe');
{
  const f = fakeFetch(200, { email: 'a@b.c', name: 'A B' });
  const result = await fetchMe({ fetchFn: f });
  assert('GET a relative /auth/me (same origin, through the proxy)',
    f.calls[0].url === '/auth/me' && f.calls[0].options.method === 'GET');
  assert('returns status and body', same(result, { status: 200, body: { email: 'a@b.c', name: 'A B' } }));
}
{
  const f = fakeFetch(401, { type: 'error', code: 'AUTH_REQUIRED', message: 'x' });
  const result = await fetchMe({ fetchFn: f });
  assert('401 is returned, not thrown', result.status === 401 && result.body.code === 'AUTH_REQUIRED');
}
{
  const f = fakeFetch(200, { email: 'a@b.c', name: 'A' });
  const controller = new AbortController();
  await fetchMe({ signal: controller.signal, fetchFn: f });
  assert('passes the abort signal to fetch', f.calls[0].options.signal === controller.signal);
}
{
  const result = await fetchMe({ fetchFn: failingFetch });
  assert('network failure -> {status: null, body: null}', same(result, { status: null, body: null }));
}
{
  const aborted = async () => { throw new DOMException('timed out', 'TimeoutError'); };
  const result = await fetchMe({ fetchFn: aborted });
  assert('timeout / abort -> {status: null, body: null}', same(result, { status: null, body: null }));
}
{
  const f = fakeFetch(502, undefined);
  const result = await fetchMe({ fetchFn: f });
  assert('non-JSON body (proxy error page) -> body null, status kept', same(result, { status: 502, body: null }));
}

console.log('signInWithGoogle');
{
  const f = fakeFetch(200, { email: 'a@b.c', name: 'A' });
  await signInWithGoogle('token-123', { fetchFn: f });
  const { url, options } = f.calls[0];
  assert('POST a relative /auth/google', url === '/auth/google' && options.method === 'POST');
  assert('sends {credential} as JSON', options.body === JSON.stringify({ credential: 'token-123' })
    && options.headers['Content-Type'] === 'application/json');
}
{
  const f = fakeFetch(403, { type: 'error', code: 'AUTH_NOT_ALLOWED', message: 'x' });
  const result = await signInWithGoogle('t', { fetchFn: f });
  assert('403 code reaches the caller', result.status === 403 && result.body.code === 'AUTH_NOT_ALLOWED');
}

console.log('logout');
{
  const f = fakeFetch(204, undefined);
  const result = await logout({ fetchFn: f });
  assert('POST a relative /auth/logout', f.calls[0].url === '/auth/logout' && f.calls[0].options.method === 'POST');
  assert('204 with no body -> {status: 204, body: null}', same(result, { status: 204, body: null }));
}
{
  const result = await logout({ fetchFn: failingFetch });
  assert('network failure -> status null', result.status === null);
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
