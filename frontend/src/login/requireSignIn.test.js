/* global process */
/**
 * requireSignIn.test.js -- the route gate's loader (requireSignIn.js), run
 * on the real module with a fake fetch. No backend, no browser.
 *
 * Covers: 401 -> a redirect to /login (thrown, as React Router expects), a
 * signed-in user returned, auth off (nulls) returned, no answer and a hung
 * /auth/me (timeout) both let the visitor in, and the router's own abort
 * signal still reaching fetch.
 *
 * Run with:
 *   node frontend/src/login/requireSignIn.test.js
 */

import { requireSignIn, NO_USER } from './requireSignIn.js';

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
const answer = (status, body) => async () => ({ status, json: async () => body });

/** A fetch that never answers on its own: it only ends when its signal aborts. */
function hangingFetch() {
  const fn = (url, options) => new Promise((_, reject) => {
    fn.signal = options.signal;
    options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
  });
  return fn;
}

const base = { signal: new AbortController().signal, timeoutMs: 1000 };

console.log('requireSignIn');
{
  let thrown = null;
  try {
    await requireSignIn({ ...base, fetchFn: answer(401, { code: 'AUTH_REQUIRED' }) });
  } catch (e) {
    thrown = e;
  }
  assert('401 throws a redirect', thrown instanceof Response);
  assert('the redirect is a 302 to /login',
    thrown && thrown.status === 302 && thrown.headers.get('Location') === '/login');
}
{
  const user = await requireSignIn({ ...base, fetchFn: answer(200, { email: 'a@b.c', name: 'A B' }) });
  assert('200 signed in -> the user', same(user, { email: 'a@b.c', name: 'A B' }));
}
{
  const user = await requireSignIn({ ...base, fetchFn: answer(200, { email: null, name: null }) });
  assert('200 auth off -> nulls (the app opens with no sign-in)', same(user, NO_USER));
}
{
  const down = async () => { throw new TypeError('Failed to fetch'); };
  const user = await requireSignIn({ ...base, fetchFn: down });
  assert('no answer -> let in, as nobody', same(user, NO_USER));
}
{
  const user = await requireSignIn({ ...base, fetchFn: answer(502, null) });
  assert('502 from the proxy (backend down) -> let in, as nobody', same(user, NO_USER));
}
{
  const f = hangingFetch();
  // In node, AbortSignal.timeout's timer does not keep the process alive by
  // itself (browsers have no such notion). This empty timer does, until the
  // check is over.
  const keepAlive = setTimeout(() => {}, 1000);
  const started = Date.now();
  const user = await requireSignIn({ signal: new AbortController().signal, timeoutMs: 30, fetchFn: f });
  const took = Date.now() - started;
  clearTimeout(keepAlive);
  assert('hung /auth/me -> let in after the timeout', same(user, NO_USER));
  assert(`gives up near timeoutMs (${took} ms, limit 30)`, took >= 25 && took < 500);
}
{
  const f = hangingFetch();
  const controller = new AbortController();
  const pending = requireSignIn({ signal: controller.signal, timeoutMs: 5000, fetchFn: f });
  controller.abort(); // the user navigated away while the check was running
  const user = await pending;
  assert('router abort reaches fetch and ends the check at once', f.signal.aborted && same(user, NO_USER));
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
