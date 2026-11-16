/* global process */
/**
 * levelHistory.test.js -- the tape's ring buffer (levelHistory.js).
 *
 * Covers: order before and after the buffer wraps, the size cap, clear.
 *
 * Run with:
 *   node frontend/src/talk/levelHistory.test.js
 */

import { createLevelHistory } from './levelHistory.js';

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

const read = (h) => {
  const out = [];
  h.forEach((t, a, b) => out.push([t, Math.round(a * 10) / 10, Math.round(b * 10) / 10]));
  return out;
};

const h = createLevelHistory(3);
assert('starts empty', h.size === 0 && read(h).length === 0);
h.push(1, 0.1, 0.2);
h.push(2, 0.3, 0.4);
assert('two samples, oldest first', JSON.stringify(read(h)) === JSON.stringify([[1, 0.1, 0.2], [2, 0.3, 0.4]]));
h.push(3, 0.5, 0.6);
h.push(4, 0.7, 0.8);
assert('size is capped at capacity', h.size === 3);
assert('after wrapping, the oldest sample is gone and order holds',
  JSON.stringify(read(h).map((r) => r[0])) === JSON.stringify([2, 3, 4]));
h.clear();
assert('clear empties it', h.size === 0 && read(h).length === 0);
h.push(9, 0, 0);
assert('works again after clear', JSON.stringify(read(h).map((r) => r[0])) === JSON.stringify([9]));

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
