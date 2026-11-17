/* global process */
/**
 * loginState.test.js -- the /login page's state logic (loginState.js).
 *
 * Covers: every answer of POST /auth/google that backend/vaani/auth.py can
 * give, a request with no answer, every answer of GET /auth/me, and the
 * first-name helper.
 *
 * Run with:
 *   node frontend/src/login/loginState.test.js
 */

import { signInResult, meResult, firstName } from './loginState.js';

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

const err = (code) => ({ type: 'error', code, message: 'x' });
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

console.log('signInResult');
assert('200 -> onair with the first name',
  same(signInResult(200, { email: 'a@b.c', name: 'Samyak Singh' }), { view: 'onair', name: 'Samyak' }));
assert('404 (auth off) -> talk', same(signInResult(404, { detail: 'Not Found' }), { view: 'talk' }));
assert('403 AUTH_NOT_ALLOWED -> refused notAllowed',
  same(signInResult(403, err('AUTH_NOT_ALLOWED')), { view: 'refused', reason: 'notAllowed' }));
assert('403 AUTH_EMAIL_UNVERIFIED -> refused unverified',
  same(signInResult(403, err('AUTH_EMAIL_UNVERIFIED')), { view: 'refused', reason: 'unverified' }));
assert('403 AUTH_BAD_ORIGIN -> error badOrigin',
  same(signInResult(403, err('AUTH_BAD_ORIGIN')), { view: 'error', reason: 'badOrigin' }));
assert('401 AUTH_INVALID_TOKEN -> error invalidToken',
  same(signInResult(401, err('AUTH_INVALID_TOKEN')), { view: 'error', reason: 'invalidToken' }));
assert('503 AUTH_UNAVAILABLE -> error googleDown',
  same(signInResult(503, err('AUTH_UNAVAILABLE')), { view: 'error', reason: 'googleDown' }));
assert('no answer (null status) -> error serverDown',
  same(signInResult(null, null), { view: 'error', reason: 'serverDown' }));
assert('500 with a non-JSON body -> error serverDown',
  same(signInResult(500, null), { view: 'error', reason: 'serverDown' }));
assert('403 with an unknown code -> error serverDown',
  same(signInResult(403, err('SOMETHING_NEW')), { view: 'error', reason: 'serverDown' }));

console.log('meResult');
assert('200 -> in (signed in, or auth off)', meResult(200) === 'in');
assert('401 -> out', meResult(401) === 'out');
assert('no answer -> unknown', meResult(null) === 'unknown');
assert('500 -> unknown', meResult(500) === 'unknown');

console.log('firstName');
assert('single name', firstName({ name: 'Samyak' }) === 'Samyak');
assert('extra spaces', firstName({ name: '  Samyak   Singh ' }) === 'Samyak');
assert('no name -> email', firstName({ name: '', email: 'a@b.c' }) === 'a@b.c');
assert('nothing -> empty', firstName(null) === '');

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
