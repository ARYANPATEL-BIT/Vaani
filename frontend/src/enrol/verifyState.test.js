/* global process */
/**
 * verifyState.test.js — tests for the verification screen's state machine
 * (enrol/verifyState.js). Pure logic only: no React, no network, no audio.
 *
 * Run with:  node frontend/src/enrol/verifyState.test.js
 */

import {
  verifyReducer, initialVerifyState, canApprove, canPlay,
} from './verifyState.js';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed++;
    process.stdout.write(`  ok   ${description}\n`);
  } else {
    failed++;
    process.stderr.write(`  FAIL ${description}\n`);
  }
}

/** Apply a list of events in order, starting from the initial state. */
function run(...events) {
  return events.reduce(verifyReducer, initialVerifyState);
}

const LOADED = { type: 'LOAD_OK', sampleUrl: 'blob:test' };

process.stdout.write('\n1. Loading:\n');
assert('starts in loading', initialVerifyState.status === 'loading');
assert('LOAD_OK -> ready with the sample url', run(LOADED).status === 'ready' && run(LOADED).sampleUrl === 'blob:test');
assert('LOAD_FAIL -> error with the message', run({ type: 'LOAD_FAIL', error: 'x' }).error === 'x' && run({ type: 'LOAD_FAIL', error: 'x' }).status === 'error');
assert('RETRY_LOAD from error -> loading, error cleared', run({ type: 'LOAD_FAIL', error: 'x' }, { type: 'RETRY_LOAD' }).status === 'loading'
  && run({ type: 'LOAD_FAIL', error: 'x' }, { type: 'RETRY_LOAD' }).error === null);
assert('a late LOAD_OK after ready is ignored', run(LOADED, { type: 'LOAD_OK', sampleUrl: 'blob:other' }).sampleUrl === 'blob:test');

process.stdout.write('\n2. Playback and the approve lock:\n');
assert('cannot approve before playing', !canApprove(run(LOADED)));
assert('cannot approve while playing for the first time', !canApprove(run(LOADED, { type: 'PLAY' })));
assert('stopping before the end keeps approve locked', !canApprove(run(LOADED, { type: 'PLAY' }, { type: 'STOPPED' })));
assert('playing to the end unlocks approve', canApprove(run(LOADED, { type: 'PLAY' }, { type: 'ENDED' })));
assert('cannot approve while replaying', !canApprove(run(LOADED, { type: 'PLAY' }, { type: 'ENDED' }, { type: 'PLAY' })));
assert('PLAY_FAIL -> ready with an error, still locked', run(LOADED, { type: 'PLAY' }, { type: 'PLAY_FAIL', error: 'e' }).status === 'ready'
  && !canApprove(run(LOADED, { type: 'PLAY' }, { type: 'PLAY_FAIL', error: 'e' })));
assert('cannot play while loading', !canPlay(initialVerifyState));
assert('cannot play in error', !canPlay(run({ type: 'LOAD_FAIL', error: 'x' })));
assert('PLAY is ignored while loading', run({ type: 'PLAY' }).status === 'loading');

process.stdout.write('\n3. Approval needs the server:\n');
const played = [LOADED, { type: 'PLAY' }, { type: 'ENDED' }];
assert('APPROVE before playing is ignored', run(LOADED, { type: 'APPROVE' }).status === 'ready');
assert('APPROVE after playing -> approving (not approved)', run(...played, { type: 'APPROVE' }).status === 'approving');
assert('APPROVE_OK -> approved', run(...played, { type: 'APPROVE' }, { type: 'APPROVE_OK' }).status === 'approved');
assert('APPROVE_FAIL -> ready with error, can retry', run(...played, { type: 'APPROVE' }, { type: 'APPROVE_FAIL', error: 'no' }).status === 'ready'
  && canApprove(run(...played, { type: 'APPROVE' }, { type: 'APPROVE_FAIL', error: 'no' })));
assert('APPROVE_OK without APPROVE is ignored', run(...played, { type: 'APPROVE_OK' }).status === 'ready');
assert('APPROVE_OK while loading is ignored', run({ type: 'APPROVE_OK' }).status === 'loading');
assert('a second APPROVE while approving is ignored', run(...played, { type: 'APPROVE' }, { type: 'APPROVE' }).status === 'approving');
assert('cannot approve while approving', !canApprove(run(...played, { type: 'APPROVE' })));

process.stdout.write('\n4. Purity:\n');
const before = JSON.stringify(initialVerifyState);
run(LOADED, { type: 'PLAY' }, { type: 'ENDED' });
assert('reducer never mutates the initial state', JSON.stringify(initialVerifyState) === before);
assert('unknown event returns the same object', verifyReducer(initialVerifyState, { type: 'NOPE' }) === initialVerifyState);

process.stdout.write(`\n--- Results: ${passed} passed, ${failed} failed ---\n`);
if (failed > 0) process.exit(1);
