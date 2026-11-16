/* global process */
/**
 * demoScript.test.js -- the landing page's scripted tape demo (demoScript.js).
 *
 * Covers:
 * 1. phaseAt: every phase boundary with the default cut, and that a moved
 *    cut moves every boundary after it.
 * 2. demoAt: Vaani's line freezes exactly where the cut fell (the "stops
 *    where you clicked" behaviour), the user's line and the reply start at
 *    their offsets from the cut, and the reduced-motion still frame is whole.
 * 3. speakerAt: which track a bar at time s belongs to.
 * 4. canCutAt, loopEnd, flashAt.
 * 5. timecode: formatting, including the float case 0.29 s.
 *
 * Run with:
 *   node frontend/src/landing/demoScript.test.js
 */

import { phaseAt, demoAt, speakerAt, canCutAt, loopEnd, flashAt, timecode } from './demoScript.js';
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
const c0 = tl.defaultCut;
const near = (a, b) => Math.abs(a - b) < 1e-9;

console.log('phaseAt, default cut');
assert('idle before Vaani starts', phaseAt(0) === 'idle');
assert('speaking from vaaniStart', phaseAt(tl.vaaniStart) === 'speak');
assert('still speaking just before the cut', phaseAt(c0 - 0.01) === 'speak');
assert('cut at the cut', phaseAt(c0) === 'cut');
assert('listening after userDelay', phaseAt(c0 + tl.userDelay) === 'you');
assert('thinking after thinkDelay', phaseAt(c0 + tl.thinkDelay) === 'think');
assert('replying after replyDelay', phaseAt(c0 + tl.replyDelay) === 'reply');
assert('idle after idleDelay', phaseAt(c0 + tl.idleDelay) === 'idle');

console.log('phaseAt, cut moved to 2.0 s');
assert('cut at 2.0', phaseAt(2.0, 2.0) === 'cut');
assert('speaking at 1.99', phaseAt(1.99, 2.0) === 'speak');
assert('listening at 2.4', phaseAt(2.0 + tl.userDelay, 2.0) === 'you');
assert('replying at 5.1', phaseAt(2.0 + tl.replyDelay, 2.0) === 'reply');
assert('default-cut time 4.8 is no longer speaking', phaseAt(c0, 2.0) !== 'speak');

console.log('demoAt');
const start = demoAt(0);
assert('nothing typed at 0', start.vaani === '' && start.user === '' && start.reply === '');
const mid = demoAt(tl.vaaniStart + tl.vaaniTyping / 2);
assert('first line partly typed halfway', mid.vaani.length > 0 && mid.vaani.length < DEMO.lines.vaani.length);
const atTwo = demoAt(1.999, 2.0).vaani;
const frozen = atTwo + '…';
assert('cut at 2.0: line freezes at what was typed, plus an ellipsis', demoAt(2.0, 2.0).vaani === frozen);
assert('cut at 2.0: still frozen at 2.5 s', demoAt(2.5, 2.0).vaani === frozen);
assert('cut at 2.0: still frozen at 9 s', demoAt(9, 2.0).vaani === frozen);
assert('cut at 2.0: frozen line is shorter than the full sentence', atTwo.length < DEMO.lines.vaani.length);
assert('cut at 2.0: user line empty before 2.4', demoAt(2.39, 2.0).user === '');
assert('cut at 2.0: user line whole by 4.3', demoAt(2.0 + tl.userDelay + tl.userTyping, 2.0).user === DEMO.lines.user);
assert('cut at 2.0: reply empty before 5.1', demoAt(5.09, 2.0).reply === '');
assert('cut at 2.0: reply started after 5.1', demoAt(5.5, 2.0).reply.length > 0);
const still = demoAt(DEMO.stillFrameAt);
assert('still frame shows the whole user line', still.user === DEMO.lines.user);
assert('still frame shows the whole reply', still.reply === DEMO.lines.reply);
assert('still frame shows the cut-off first line', still.vaani.endsWith('…'));

console.log('speakerAt, cut at 2.0');
assert('vaani at 1.0', speakerAt(1.0, 2.0) === 'vaani');
assert('silence at 2.2 (between cut and user)', speakerAt(2.2, 2.0) === '');
assert('user at 3.0', speakerAt(3.0, 2.0) === 'user');
assert('silence at 4.6 (thinking)', speakerAt(4.6, 2.0) === '');
assert('vaani again at 6.0 (the reply)', speakerAt(6.0, 2.0) === 'vaani');
assert('silence at 8.4 (idle)', speakerAt(8.4, 2.0) === '');

console.log('canCutAt');
assert('not before earliestCut', canCutAt(0.5) === false);
assert('yes at 1.0', canCutAt(1.0) === true);
assert('not at the cut', canCutAt(c0) === false);
assert('not after a moved cut', canCutAt(3.0, 2.0) === false);

console.log('loopEnd');
assert('cut at 2.0 -> 10.6', near(loopEnd(2.0), 2.0 + tl.loopTail));
assert('default cut -> 13.4', near(loopEnd(), c0 + tl.loopTail));

console.log('flashAt');
assert('no flash before the cut', flashAt(c0 - 0.01) === 0);
assert('full flash at the cut', flashAt(c0) === 1);
assert('no flash after flashS', flashAt(c0 + tl.flashS) === 0);

console.log('timecode');
assert('4.8 -> 00:04.80', timecode(4.8) === '00:04.80');
assert('0.29 -> 00:00.29', timecode(0.29) === '00:00.29');
assert('65.25 -> 01:05.25', timecode(65.25) === '01:05.25');
assert('negative -> 00:00.00', timecode(-1) === '00:00.00');

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
