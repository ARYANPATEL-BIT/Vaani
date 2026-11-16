/**
 * drawTape.js -- paints one frame of the two-track tape onto a canvas.
 *
 * Nothing is remembered between frames. Every bar is recomputed from time:
 * bar number k was "recorded" at time k * dt, has slid left at a constant
 * speed since then, so its x position today is
 *     x = playhead - (t - k * dt) * speed.
 * Which track it sits on comes from speakerAt(k * dt, cut), and its height
 * from a fixed formula of k. So moving the cut instantly re-colours the
 * past correctly, and there is no growing array to trim.
 *
 * Called by useTape.js every animation frame (or once, for the still frame).
 */

import { PALETTE, TAPE } from './landingContent.js';
import { speakerAt, flashAt, timecode } from './demoScript.js';
import { fitCanvas } from './canvasSize.js';

const C = TAPE.colours;

// A bar's height, 0.07..1, from its index. Fixed per k, so a bar keeps its
// shape while it slides; the mix of sines just makes it look like speech.
function amplitude(k) {
  const a = 0.25 + 0.75 * Math.abs(Math.sin(k * 1.7) * Math.cos(k * 0.37));
  return a * (0.55 + 0.45 * Math.sin(k * 0.21) ** 2);
}

export function drawTape(canvas, t, cut, phase) {
  const fit = fitCanvas(canvas, TAPE.maxDpr, TAPE.maxCanvasPx);
  if (!fit) return; // not laid out yet: skip this frame
  const { g, w, h } = fit;
  g.clearRect(0, 0, w, h);

  const px = Math.round(w * TAPE.playheadAt); // the playhead: "now"
  const sp = TAPE.speedPxPerS;
  const v = Math.max(sp.min, Math.min(sp.max, w * sp.perWidth)); // px per second
  const dt = TAPE.barGapPx / v; // seconds between two bars
  const y1 = h * 0.29;          // Vaani's track centre
  const y2 = h * 0.76;          // the user's track centre
  const half = h * 0.17;        // the tallest bar reaches this far up and down

  // The future, right of the playhead, is a shade darker.
  g.fillStyle = C.future;
  g.fillRect(px, 0, w - px, h);

  // The dashed divider and the two track baselines.
  g.lineWidth = 1;
  g.strokeStyle = C.divider;
  g.setLineDash([3, 4]);
  g.beginPath(); g.moveTo(0, h * 0.53); g.lineTo(w, h * 0.53); g.stroke();
  g.setLineDash([]);
  g.strokeStyle = C.baseline;
  g.beginPath(); g.moveTo(0, y1); g.lineTo(w, y1); g.moveTo(0, y2); g.lineTo(w, y2); g.stroke();

  // One tick per second along the top, with its timecode.
  g.font = '10px "Vaani Mono", ui-monospace, monospace';
  g.fillStyle = C.ticks;
  const firstS = Math.max(0, Math.floor(t - px / v));
  const lastS = Math.ceil(t + (w - px) / v);
  for (let s = firstS; s <= lastS; s++) {
    const x = px + (s - t) * v;
    g.fillRect(x, 0, 1, 7);
    g.fillText(timecode(s).slice(0, 5), x + 4, 12);
  }

  // The bars: only the ones between the left edge and the playhead exist.
  const k0 = Math.max(0, Math.ceil((t - px / v) / dt));
  const k1 = Math.floor(t / dt);
  for (let k = k0; k <= k1; k++) {
    const who = speakerAt(k * dt, cut);
    if (!who) continue; // silence: no bar
    const x = px - (t - k * dt) * v;
    const bh = Math.max(2, amplitude(k) * half * 2);
    const age = x / px; // 1 at the playhead, 0 at the left edge: older is fainter
    if (who === 'vaani') {
      g.fillStyle = `rgba(${C.vaani},${(0.3 + 0.7 * age).toFixed(3)})`;
      g.fillRect(x, y1 - bh / 2, TAPE.barWidthPx, bh);
    } else {
      g.fillStyle = PALETTE.red;
      g.globalAlpha = 0.45 + 0.55 * age;
      g.fillRect(x, y2 - bh / 2, TAPE.barWidthPx, bh);
      g.globalAlpha = 1;
    }
  }

  // Thinking: three dots pulse just after the playhead on Vaani's track.
  if (phase === 'think') {
    for (let d = 0; d < 3; d++) {
      g.fillStyle = `rgba(${C.vaani},${(0.3 + 0.7 * Math.abs(Math.sin(t * 5 + d))).toFixed(3)})`;
      g.beginPath(); g.arc(px + 14 + d * 12, y1, 3, 0, Math.PI * 2); g.fill();
    }
  }

  // The cut: a red line on the tape where the user came in, with its timecode,
  // and a short red flash over everything right after it.
  if (t >= cut) {
    const flash = flashAt(t, cut);
    if (flash > 0) {
      g.fillStyle = PALETTE.red;
      g.globalAlpha = 0.22 * flash;
      g.fillRect(0, 0, w, h);
      g.globalAlpha = 1;
    }
    const cx = px - (t - cut) * v;
    if (cx > -80) { // still (partly) on screen
      const label = `CUT ${timecode(cut)}`;
      g.fillStyle = PALETTE.red;
      g.fillRect(cx - 1, 18, 2, h - 18);
      g.fillRect(cx - 1, 18, g.measureText(label).width + 12, 18);
      g.fillStyle = C.cutText;
      g.fillText(label, cx + 5, 31);
    }
  }

  // The playhead (a line with a small triangle) and the running timecode.
  g.fillStyle = C.playhead;
  g.fillRect(px - 1, 0, 2, h);
  g.beginPath(); g.moveTo(px - 6, 0); g.lineTo(px + 6, 0); g.lineTo(px, 8); g.closePath(); g.fill();
  g.font = '12px "Vaani Mono", ui-monospace, monospace';
  g.fillText(timecode(t), px + 10, h - 10);

  // Old tape fades into the background on the left.
  const fade = g.createLinearGradient(0, 0, TAPE.fadePx, 0);
  fade.addColorStop(0, `rgba(${C.fade},1)`);
  fade.addColorStop(1, `rgba(${C.fade},0)`);
  g.fillStyle = fade;
  g.fillRect(0, 0, TAPE.fadePx, h);
}
