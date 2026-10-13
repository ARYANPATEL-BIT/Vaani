/* global process */
/**
 * pttPress.test.js — the push-to-talk press states (pttPress.js,
 * docs/contracts.md §2.8).
 *
 * Covers:
 * 1. A normal press: ptt.start, frames while holding and stopping,
 *    ptt.end only after the worklet's last frame.
 * 2. Ignored presses: speak while holding or stopping, stop while idle.
 * 3. The fallback: no worklet answer after fallbackMs sends ptt.end anyway,
 *    with a warning; a late answer afterwards sends nothing.
 * 4. reset() drops an open press without sending anything.
 *
 * Run with:
 *   node frontend/src/ptt/pttPress.test.js
 */

import { createPttPress, PRESS_STATES } from './pttPress.js';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${description}`);
  } else {
    failed += 1;
    console.error(`  FAIL ${description}`);
  }
}

/** A press wired to fakes: records sends, requests, warnings and the timer. */
function makePress() {
  const rig = {
    sent: [],
    lastFrameRequests: 0,
    warnings: [],
    states: [],
    timer: null, // { fn, ms } while a fallback is pending
    cleared: 0,
  };
  rig.press = createPttPress({
    send: (msg) => rig.sent.push(msg.type),
    requestLastFrame: () => {
      rig.lastFrameRequests += 1;
    },
    fallbackMs: 300,
    onChange: (state) => rig.states.push(state),
    setTimer: (fn, ms) => {
      rig.timer = { fn, ms };
      return 'timer-1';
    },
    clearTimer: (id) => {
      if (id === 'timer-1') rig.cleared += 1;
      rig.timer = null;
    },
    warn: (text) => rig.warnings.push(text),
  });
  return rig;
}

console.log('=== Push-to-talk press states ===\n');

console.log('1. A normal press:');
{
  const rig = makePress();
  const { press } = rig;
  assert('starts idle', press.state === PRESS_STATES.IDLE);
  assert('no frames while idle', press.sendsFrames() === false);
  assert('start() opens a press', press.start() === true);
  assert('ptt.start sent', rig.sent.join(',') === 'ptt.start');
  assert('frames pass while holding', press.sendsFrames() === true);
  assert('stop() begins closing', press.stop() === true);
  assert('worklet asked for its last frame', rig.lastFrameRequests === 1);
  assert('fallback armed at 300 ms', rig.timer !== null && rig.timer.ms === 300);
  assert('frames still pass while stopping', press.sendsFrames() === true);
  assert('no ptt.end before the last frame', rig.sent.join(',') === 'ptt.start');
  press.lastFrameSent();
  assert('ptt.end sent after the last frame', rig.sent.join(',') === 'ptt.start,ptt.end');
  assert('fallback cancelled', rig.cleared === 1 && rig.timer === null);
  assert('back to idle', press.state === PRESS_STATES.IDLE);
  assert('no frames after the press', press.sendsFrames() === false);
  assert(
    'states reported in order',
    rig.states.join(',') === 'holding,stopping,idle',
  );
  assert('no warning on a normal press', rig.warnings.length === 0);
}

console.log('\n2. Ignored presses:');
{
  const rig = makePress();
  const { press } = rig;
  assert('stop while idle is ignored', press.stop() === false && rig.sent.length === 0);
  press.start();
  assert('speak while holding is ignored (key repeat)', press.start() === false);
  assert('only one ptt.start sent', rig.sent.join(',') === 'ptt.start');
  press.stop();
  assert('speak while stopping is ignored', press.start() === false);
  assert('stop while stopping is ignored', press.stop() === false);
  assert('worklet asked only once', rig.lastFrameRequests === 1);
  press.lastFrameSent();
  press.lastFrameSent();
  assert('a second last-frame answer sends nothing', rig.sent.join(',') === 'ptt.start,ptt.end');
  assert('a new press can start after the end', press.start() === true);
}

console.log('\n3. Fallback when the worklet never answers:');
{
  const rig = makePress();
  const { press } = rig;
  press.start();
  press.stop();
  rig.timer.fn(); // 300 ms pass with no answer
  assert('ptt.end sent by the fallback', rig.sent.join(',') === 'ptt.start,ptt.end');
  assert('one warning logged', rig.warnings.length === 1);
  assert('warning names the wait', rig.warnings[0].includes('300 ms'));
  assert('back to idle', press.state === PRESS_STATES.IDLE);
  press.lastFrameSent(); // the late answer
  assert('late answer sends no second ptt.end', rig.sent.join(',') === 'ptt.start,ptt.end');
  assert('late answer does not reopen frames', press.sendsFrames() === false);
}

console.log('\n4. reset() on disconnect:');
{
  const rig = makePress();
  const { press } = rig;
  press.start();
  press.stop();
  press.reset();
  assert('nothing sent by reset', rig.sent.join(',') === 'ptt.start');
  assert('fallback cancelled by reset', rig.timer === null);
  assert('idle after reset', press.state === PRESS_STATES.IDLE);
}

console.log(`\n--- Results: ${passed} passed, ${failed} failed ---`);

if (failed > 0) {
  process.exit(1);
}
