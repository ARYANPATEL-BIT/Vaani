/**
 * drawStudioTape.js -- paints one frame of the Studio's live tape.
 *
 * The tape is a time axis. Every bar is one level sample (levelHistory.js)
 * placed at the second it was taken. The playhead walks right until it
 * reaches TAPE.headFrac of the width; after that the window slides, so the
 * newest bar is always at the playhead and older bars move left.
 *
 *   ruler   | 00:01 | 00:02 | ... (one tick per second)
 *   track 1 | Vaani: playback loudness, grey (newest bars bright)
 *   track 2 | You: mic loudness, dark red (newest bars bright red)
 *
 * Nothing here keeps state between frames: given the same inputs it draws
 * the same picture. Used only by useStudioTape.js.
 */

import { fitCanvas } from '../landing/canvasSize.js';
import { TAPE } from './talkContent.js';
import { timecode } from './studioState.js';

const C = TAPE.colors;

// Bar height for a loudness value, as a fraction of the track (0..1).
// sqrt lifts quiet speech so it is still visible; the gain sets how loud
// "full height" is.
const barFrac = (level) => Math.min(1, Math.sqrt(level) * TAPE.levelGain);

function dashedLine(g, x1, y1, x2, y2) {
  g.setLineDash([3, 3]);
  g.beginPath();
  g.moveTo(x1, y1);
  g.lineTo(x2, y2);
  g.stroke();
  g.setLineDash([]);
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {object} f
 * @param {object} f.history   levelHistory
 * @param {number} f.now       session seconds at the playhead
 * @param {number[]} f.cuts    session seconds of every barge-in seen
 * @param {boolean} f.thinking show the three dots after the playhead
 * @param {number} f.dotsLit   how many of the three dots are lit (0..3)
 */
export function drawStudioTape(canvas, { history, now, cuts, thinking, dotsLit }) {
  const fit = fitCanvas(canvas, TAPE.maxDpr);
  if (!fit) return; // not laid out yet (or hidden): skip this frame
  const { g, w, h } = fit;
  g.clearRect(0, 0, w, h);

  const top = TAPE.rulerPx;
  const trackH = (h - top) / 2;
  const midVaani = top + trackH / 2;
  const midYou = top + trackH + trackH / 2;
  const pxPerS = TAPE.pxPerS;
  const windowS = w / pxPerS; // seconds that fit across this canvas
  const headX = Math.min(now * pxPerS, w * TAPE.headFrac);
  const viewStart = now - headX / pxPerS; // session second at the left edge
  const xOf = (t) => (t - viewStart) * pxPerS;

  // Ruler and track guides.
  g.strokeStyle = C.rule;
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(0, top - 0.5);
  g.lineTo(w, top - 0.5);
  g.stroke();
  dashedLine(g, 0, top + trackH, w, top + trackH);
  dashedLine(g, 0, midVaani, w, midVaani);
  dashedLine(g, 0, midYou, w, midYou);
  g.font = TAPE.font;
  g.fillStyle = C.rulerText;
  for (let s = Math.max(1, Math.ceil(viewStart)); s <= viewStart + windowS; s++) {
    const x = Math.round(xOf(s)) + 0.5;
    g.beginPath();
    g.moveTo(x, 0);
    g.lineTo(x, top);
    g.stroke();
    g.fillText(timecode(s).slice(0, 5), x + 6, 16);
  }

  // Bars: one per sample inside the window. Each track's bar is centred on
  // its middle line and drawn only if the sample was loud enough.
  history.forEach((t, vaani, you) => {
    if (t < viewStart || t > now) return;
    const x = xOf(t) - TAPE.barPx / 2;
    const recent = now - t < TAPE.recentS;
    if (vaani >= TAPE.minLevel) {
      const bh = barFrac(vaani) * trackH * 0.9;
      g.fillStyle = recent ? C.vaaniNow : C.vaani;
      g.fillRect(x, midVaani - bh / 2, TAPE.barPx, bh);
    }
    if (you >= TAPE.minLevel) {
      const bh = barFrac(you) * trackH * 0.9;
      g.fillStyle = recent ? C.youNow : C.you;
      g.fillRect(x, midYou - bh / 2, TAPE.barPx, bh);
    }
  });

  // Thinking: three dots just after the playhead on Vaani's track.
  if (thinking) {
    g.fillStyle = C.head;
    for (let k = 0; k < dotsLit; k++) {
      g.beginPath();
      g.arc(headX + 13 + k * 12, midVaani, 3, 0, Math.PI * 2);
      g.fill();
    }
  }

  // Cut markers: a red line and a "CUT 00:09.18" flag on the ruler. The
  // flag flips to the line's left near the right edge so it stays visible.
  g.font = TAPE.font;
  for (const c of cuts) {
    if (c < viewStart || c > now) continue;
    const x = Math.round(xOf(c));
    g.fillStyle = C.cut;
    g.fillRect(x - 1, 0, 2, h);
    const label = `CUT ${timecode(c)}`;
    const lw = g.measureText(label).width + 14;
    const lx = x + 4 + lw > w ? x - 4 - lw : x + 4;
    g.fillRect(lx, 4, lw, 17);
    g.fillStyle = C.cutText;
    g.fillText(label, lx + 7, 16);
  }

  // Playhead: a line, a triangle on top, and the running timecode.
  g.fillStyle = C.head;
  g.fillRect(headX - 1, top - 8, 2, h - top + 8);
  g.beginPath();
  g.moveTo(headX - 7, top - 8);
  g.lineTo(headX + 7, top - 8);
  g.lineTo(headX, top + 1);
  g.closePath();
  g.fill();
  g.font = TAPE.headFont;
  const tc = timecode(now);
  const tw = g.measureText(tc).width;
  g.fillText(tc, headX + 10 + tw > w ? headX - 10 - tw : headX + 10, h - 10);
}
