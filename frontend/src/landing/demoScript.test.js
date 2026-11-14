/* global process */
/**
 * demoScript.test.js -- the landing page's scripted demo (demoScript.js).
 *
 * Covers:
 * 1. phaseAt: each phase starts and ends at the timeline's boundaries.
 * 2. demoAt: text types out, the first answer is cut off with an ellipsis,
 *    the user's line and the reply appear only after their start times.
 * 3. loopTime: negative time (preloader) is held at 0; time wraps per loop.
 * 4. flashAt: the cut flash is only lit between the cut and its end.
 *
 * Run with:
 *   node frontend/src/landing/demoScript.test.js
 */

import { phaseAt, demoAt, loopTime, flashAt } from './demoScript.js';
import { DEMO } from './landingContent.js';

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

const tl = DEMO.timeline;

console.log('phaseAt');
assert('speaks at the start', phaseAt(0) === 'speak');
assert('still speaking just before the cut', phaseAt(tl.cut - 0.01) === 'speak');
assert('cut at the cut', phaseAt(tl.cut) === 'cut');
assert('listening after the cut', phaseAt(tl.listen) === 'listen');
assert('thinking after listening', phaseAt(tl.think) === 'think');
assert('speaks the reply', phaseAt(tl.replyStart) === 'speak');
assert('idle at the end', phaseAt(tl.idle) === 'idle');

console.log('demoAt');
const start = demoAt(0);
assert('nothing typed before the first line starts', start.vaani === '' && start.user === '' && start.reply === '');
const mid = demoAt(tl.vaaniStart + tl.vaaniTyping / 2);
assert('first line is partly typed halfway', mid.vaani.length > 0 && mid.vaani.length < DEMO.lines.vaani.length);
const cut = demoAt(tl.cut);
assert('first line ends in an ellipsis once cut', cut.vaani === DEMO.lines.vaani + '\u2026');
assert('user line not shown before it starts', cut.user === '');
const still = demoAt(DEMO.stillFrameAt);
assert('still frame shows the whole user line', still.user === DEMO.lines.user);
assert('still frame shows the whole reply', still.reply === DEMO.lines.reply);

console.log('loopTime');
assert('negative time is held at 0', loopTime(-2) === 0);
assert('time wraps after one loop', Math.abs(loopTime(tl.loop + 1) - 1) < 1e-9);

console.log('flashAt');
assert('no flash before the cut', flashAt(tl.cut - 0.01) === 0);
assert('full flash at the cut', flashAt(tl.cut) === 1);
assert('no flash after it ends', flashAt(tl.flashEnd) === 0);

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
