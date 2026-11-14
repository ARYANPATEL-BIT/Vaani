/**
 * demoScript.js -- what the scripted demo shows at a moment in its loop.
 *
 * Pure functions: a time in, the text and phase out. No timers, no React.
 * The hero wave and the demo card both call demoAt with the same time, so
 * the ribbons and the words cannot drift apart.
 */

import { DEMO } from './landingContent.js';

const clamp01 = (x) => Math.max(0, Math.min(1, x));

// The first part of `text` that has "typed out" by time t.
function typed(text, t, start, duration) {
  return text.slice(0, Math.round(clamp01((t - start) / duration) * text.length));
}

// Total time the page has run (negative while the preloader still covers
// the hero) -> seconds into the current loop.
export function loopTime(elapsed, demo = DEMO) {
  return Math.max(0, elapsed) % demo.timeline.loop;
}

// Which phase the demo is in at time t.
export function phaseAt(t, demo = DEMO) {
  const tl = demo.timeline;
  if (t < tl.cut) return 'speak';
  if (t < tl.listen) return 'cut';
  if (t < tl.think) return 'listen';
  if (t < tl.replyStart) return 'think';
  if (t < tl.idle) return 'speak';
  return 'idle';
}

// The three transcript lines and the phase at time t.
export function demoAt(t, demo = DEMO) {
  const tl = demo.timeline;
  const { lines } = demo;
  // Once cut off, the first answer shows in full, ending in an ellipsis.
  const vaani = t >= tl.cut
    ? lines.vaani + '\u2026'
    : typed(lines.vaani, t, tl.vaaniStart, tl.vaaniTyping);
  const user = t >= tl.userStart ? typed(lines.user, t, tl.userStart, tl.userTyping) : '';
  const reply = t >= tl.replyStart ? typed(lines.reply, t, tl.replyStart, tl.replyTyping) : '';
  return { vaani, user, reply, phase: phaseAt(t, demo) };
}

// Brightness (0 to 1) of the white line that flashes when the user cuts in.
export function flashAt(t, demo = DEMO) {
  const { cut, flashEnd } = demo.timeline;
  if (t < cut || t >= flashEnd) return 0;
  return 1 - (t - cut) / (flashEnd - cut);
}
