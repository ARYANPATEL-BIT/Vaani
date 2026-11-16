/**
 * demoScript.js -- what the scripted tape demo shows at a moment in its loop.
 *
 * Pure functions: a time and a cut in, text and phase out. No timers, no
 * React, no canvas. useTape.js (the animation loop), drawTape.js (the
 * canvas) and LiveTape.jsx (the captions) all call these with the same
 * (t, cut), so the bars, the captions and the button cannot disagree.
 *
 * `t` is seconds into the current loop. `cut` is the second at which the
 * user cut in: the default from landingContent.js, or "now" when the visitor
 * pressed Cut in. Everything after the cut is timed from the cut.
 */

import { DEMO } from './landingContent.js';

const TL = DEMO.timeline;
const clamp01 = (x) => Math.max(0, Math.min(1, x));

// The first part of `text` that has "typed out" by time t.
function typed(text, t, start, duration) {
  return text.slice(0, Math.round(clamp01((t - start) / duration) * text.length));
}

// Which phase the demo is in at time t.
export function phaseAt(t, cut = TL.defaultCut) {
  if (t < TL.vaaniStart) return 'idle';
  if (t < cut) return 'speak';
  if (t < cut + TL.userDelay) return 'cut';
  if (t < cut + TL.thinkDelay) return 'you';
  if (t < cut + TL.replyDelay) return 'think';
  if (t < cut + TL.idleDelay) return 'reply';
  return 'idle';
}

// The three caption lines and the phase at time t.
export function demoAt(t, cut = TL.defaultCut) {
  const { lines } = DEMO;
  // After the cut, Vaani's line is frozen at exactly what it had typed when
  // the cut happened, plus an ellipsis: it stopped mid-word.
  const vaani = t < cut
    ? typed(lines.vaani, t, TL.vaaniStart, TL.vaaniTyping)
    : typed(lines.vaani, cut, TL.vaaniStart, TL.vaaniTyping) + '…';
  const user = typed(lines.user, t, cut + TL.userDelay, TL.userTyping);
  const reply = typed(lines.reply, t, cut + TL.replyDelay, TL.replyTyping);
  return { vaani, user, reply, phase: phaseAt(t, cut) };
}

// Who was making sound at time s: 'vaani', 'user' or '' (silence). The tape
// asks this for every bar it draws, so the bars need no stored array.
export function speakerAt(s, cut = TL.defaultCut) {
  if (s >= TL.vaaniStart && s < cut) return 'vaani';
  if (s >= cut + TL.userDelay && s < cut + TL.thinkDelay) return 'user';
  if (s >= cut + TL.replyDelay && s < cut + TL.idleDelay) return 'vaani';
  return '';
}

// Whether the Cut in button can be pressed at time t: only while Vaani is
// still on her first sentence and the cut has not happened yet.
export function canCutAt(t, cut = TL.defaultCut) {
  return t >= TL.earliestCut && t < cut;
}

// The loop restarts (and the cut goes back to the default) at this time.
export function loopEnd(cut = TL.defaultCut) {
  return cut + TL.loopTail;
}

// Strength (1 down to 0) of the red flash just after the cut.
export function flashAt(t, cut = TL.defaultCut) {
  if (t < cut || t >= cut + TL.flashS) return 0;
  return 1 - (t - cut) / TL.flashS;
}

// Seconds -> "mm:ss.cc". Works in whole centiseconds, so 0.29 s prints as
// "00:00.29" (multiplying the float first would give 28.999... and ".28").
export function timecode(seconds) {
  const cs = Math.round(Math.max(0, seconds) * 100);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(Math.floor(cs / 6000))}:${pad(Math.floor(cs / 100) % 60)}.${pad(cs % 100)}`;
}
