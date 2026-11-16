/* global process */
/**
 * studioState.test.js -- the Studio page's view logic (studioState.js).
 *
 * Covers: every wsStatus / turnState pair that picks a view, the CUT latch,
 * which messages count as a cut, timecode formatting and the line tail.
 *
 * Run with:
 *   node frontend/src/talk/studioState.test.js
 */

import { viewFor, cutStillLatched, isCutMessage, timecode, tail } from './studioState.js';

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

const v = (wsStatus, turnState = 'idle', fatal = false, cutLatched = false) =>
  viewFor({ wsStatus, turnState, fatal, cutLatched });

console.log('viewFor');
assert('disconnected -> standby', v('disconnected') === 'standby');
assert('connecting -> tuning', v('connecting') === 'tuning');
assert('connected (no session.started yet) -> tuning', v('connected') === 'tuning');
assert('socket error -> offair', v('error') === 'offair');
assert('mic denied (disconnected + fatal) -> offair', v('disconnected', 'idle', true) === 'offair');
assert('ready + idle -> ready', v('ready', 'idle') === 'ready');
assert('ready + listening -> listening', v('ready', 'listening') === 'listening');
assert('ready + thinking -> thinking', v('ready', 'thinking') === 'thinking');
assert('ready + speaking -> speaking', v('ready', 'speaking') === 'speaking');
assert('ready + cancelling -> cut', v('ready', 'cancelling') === 'cut');
assert('ready + listening + latched -> cut', v('ready', 'listening', false, true) === 'cut');
assert('a per-turn error while ready keeps the live view', v('ready', 'thinking', true) === 'thinking');

console.log('cutStillLatched');
assert('holds through cancelling', cutStillLatched('cancelling'));
assert('holds through the new listening turn', cutStillLatched('listening'));
assert('clears at thinking', !cutStillLatched('thinking'));
assert('clears at speaking', !cutStillLatched('speaking'));
assert('clears at idle', !cutStillLatched('idle'));

console.log('isCutMessage');
assert('audio.flush is a cut', isCutMessage({ type: 'audio.flush', turn_id: 't1' }));
assert('turn.state cancelling is a cut', isCutMessage({ type: 'turn.state', state: 'cancelling' }));
assert('turn.state speaking is not', !isCutMessage({ type: 'turn.state', state: 'speaking' }));
assert('null is not', !isCutMessage(null));

console.log('timecode');
assert('9.18 -> 00:09.18', timecode(9.18) === '00:09.18');
assert('65.25 -> 01:05.25', timecode(65.25) === '01:05.25');
assert('negative -> 00:00.00', timecode(-1) === '00:00.00');

console.log('tail');
assert('short text unchanged', tail('Hello there', 40) === 'Hello there');
assert('long text starts at a word, with …', tail('one two three four five', 10) === '…four five');
assert('empty -> empty', tail(null, 10) === '');

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
