/**
 * drawRibbons.js -- the hero's three glowing ribbons (ported from the
 * mockup's draw() in docs/design/landing/Main.dc.html).
 *
 * Pure drawing: no React, no timers. HeroWave.jsx decides when to call it.
 *
 * Each ribbon is the surface between two wavy edge curves. The curves run at
 * slightly different speeds, so they cross; each crossing is a "twist", and
 * a bloom of light is drawn there.
 *
 * The glow comes from additive blending ('lighter'): wherever two strokes
 * overlap, their colours are added, so overlaps get brighter and whiter,
 * the way light does. No blur filter is used: wide faint strokes under a
 * thin bright one fake a glow far more cheaply.
 */

// The art itself: phase, speed, frequency, edge amplitudes, offsets, how
// opaque the body and strands are, how many strands, edge brightness, and
// the two edge colours. Back ribbon first.
const RIBBONS = [
  { p: 2.0, sp: 0.55, fr: 0.72, f2: 0.9, a1: 1.2, a2: 0.8, lag: 1.5, off: -0.04, fill: 0.05, line: 0.09, lines: 24, edge: 0.14, c1: [118, 98, 255], c2: [160, 96, 255] },
  { p: 3.6, sp: 0.8, fr: 0.9, f2: 1.16, a1: 0.85, a2: 1.0, lag: -1.1, off: 0.05, fill: 0.16, line: 0.12, lines: 26, edge: 0.4, c1: [184, 112, 255], c2: [112, 140, 255] },
  { p: 0.5, sp: 1.0, fr: 1.0, f2: 0.8, a1: 1.0, a2: 0.92, lag: 1.25, off: 0, fill: 0.42, line: 0.26, lines: 38, edge: 1, c1: [128, 176, 255], c2: [196, 112, 255] },
];
// Edge glow passes: [line width in px, opacity]. Wide and faint first.
const GLOW_PASSES = [[34, 0.03], [20, 0.055], [10, 0.1], [4.5, 0.24]];
const WHITE = [240, 244, 255];
const SKY = [140, 196, 255];
const PINK = [214, 140, 255];

function rgba(c, a) {
  return `rgba(${c[0]},${c[1]},${c[2]},${Math.max(0, Math.min(1, a)).toFixed(3)})`;
}

// Advance the wave's state by dt seconds. `wave` holds amp (0 flat to 1 full)
// and ph (the wave's own phase). The phase advances faster when loud, so a
// quiet wave slows down instead of jumping.
export function stepWave(wave, phase, dt, cfg) {
  const target = cfg.amplitude[phase];
  const rate = phase === 'cut' ? cfg.easeCut : cfg.easeOther;
  // Close `rate` of the gap per 60 Hz frame, whatever the real frame rate,
  // so a 120 Hz screen does not ease twice as fast.
  const k = 1 - Math.pow(1 - rate, dt * 60);
  wave.amp += (target - wave.amp) * k;
  wave.ph += dt * (0.22 + wave.amp * 0.95);
}

// Draw one frame. g is a context already scaled to CSS pixels (canvasSize.js).
export function drawRibbons(g, w, h, amp, ph, flash) {
  g.clearRect(0, 0, w, h);
  const geo = {
    w, h, amp, ph,
    k: (Math.PI * 2 * Math.max(0.8, Math.min(2.05, w / 900))) / w, // 0.8 to 2 waves across
    cy: h * 0.5,
    A: Math.min(h * 0.26, w * 0.17) * (0.2 + 0.8 * amp), // gentler on a narrow phone
    step: Math.max(5, Math.round(w / 280)),               // px between curve points
  };
  geo.n = Math.ceil(w / geo.step) + 3;
  g.globalCompositeOperation = 'lighter'; // light adds up where ribbons overlap
  g.lineJoin = 'round';
  for (const rb of RIBBONS) drawRibbon(g, rb, geo);
  // The moment of interruption: one thin white line flashes across.
  if (flash > 0) {
    const line = g.createLinearGradient(0, 0, w, 0);
    line.addColorStop(0, 'rgba(255,255,255,0)');
    line.addColorStop(0.5, rgba([255, 255, 255], 0.9 * flash));
    line.addColorStop(1, 'rgba(255,255,255,0)');
    g.strokeStyle = line;
    g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(0, geo.cy); g.lineTo(w, geo.cy); g.stroke();
  }
  g.globalCompositeOperation = 'source-over'; // back to normal painting
}

function tracePath(g, ys, geo) {
  g.beginPath();
  for (let i = 0; i < geo.n; i++) {
    const x = (i - 1) * geo.step;
    if (i === 0) g.moveTo(x, ys[i]); else g.lineTo(x, ys[i]);
  }
}

function drawRibbon(g, rb, geo) {
  const { w, h, amp, ph, k, cy, A, step, n } = geo;
  // The two edges, T (top) and B (bottom), and where they cross.
  const T = new Array(n);
  const B = new Array(n);
  const crossings = [];
  for (let i = 0; i < n; i++) {
    const x = (i - 1) * step;
    const th = k * x * rb.fr + rb.p + ph * rb.sp;
    // The second edge runs at its own pace, so the twists are uneven.
    const th2 = k * x * rb.fr * rb.f2 + rb.p - rb.lag + ph * rb.sp * 0.9;
    T[i] = cy + h * rb.off + A * rb.a1 * Math.sin(th) + A * 0.1 * Math.sin(th * 2.1 + rb.p - ph * 0.6);
    B[i] = cy + h * rb.off + A * rb.a2 * Math.sin(th2) + A * 0.09 * Math.sin(th * 1.7 + ph * 0.45);
    if (i > 0 && (T[i] - B[i]) * (T[i - 1] - B[i - 1]) < 0) {
      crossings.push([x - step * 0.5, (T[i] + B[i]) * 0.5]);
    }
  }

  // A soft halo hugging the brighter ribbons.
  if (rb.edge >= 0.4) {
    tracePath(g, T.map((t, i) => (t + B[i]) * 0.5), geo);
    g.strokeStyle = rgba([110, 76, 255], 0.035 * rb.edge); g.lineWidth = h * 0.3; g.stroke();
    g.strokeStyle = rgba([110, 86, 255], 0.05 * rb.edge); g.lineWidth = h * 0.16; g.stroke();
  }

  // Translucent body: along the top edge, back along the bottom edge.
  const body = g.createLinearGradient(0, 0, w, 0);
  body.addColorStop(0, rgba([104, 60, 255], rb.fill));
  body.addColorStop(0.3, rgba([72, 92, 255], rb.fill * 0.85));
  body.addColorStop(0.55, rgba([124, 70, 255], rb.fill));
  body.addColorStop(0.8, rgba([168, 76, 255], rb.fill * 0.9));
  body.addColorStop(1, rgba([84, 80, 255], rb.fill));
  g.fillStyle = body;
  g.beginPath();
  for (let i = 0; i < n; i++) {
    if (i === 0) g.moveTo(-step, T[0]); else g.lineTo((i - 1) * step, T[i]);
  }
  for (let i = n - 1; i >= 0; i--) g.lineTo((i - 1) * step, B[i]);
  g.closePath(); g.fill();

  // Fine strands across the surface, bunched toward the lit edge.
  g.lineWidth = 0.8;
  const ys = new Array(n);
  for (let j = 1; j < rb.lines; j++) {
    const f = Math.pow(j / rb.lines, 1.5);
    for (let i = 0; i < n; i++) ys[i] = T[i] + (B[i] - T[i]) * f;
    g.strokeStyle = rgba([186, 170, 255], rb.line * (0.45 + 0.9 * (1 - f)));
    tracePath(g, ys, geo); g.stroke();
  }

  // Glowing edges: wide faint passes under one thin bright pass.
  for (const [edge, colour, weight] of [[T, rb.c1, 1], [B, rb.c2, 0.75]]) {
    const strength = rb.edge * weight;
    tracePath(g, edge, geo);
    for (const [width, alpha] of GLOW_PASSES) {
      g.lineWidth = width; g.strokeStyle = rgba(colour, alpha * strength); g.stroke();
    }
    const hot = g.createLinearGradient(0, 0, w, 0);
    hot.addColorStop(0, rgba(colour, 0.7 * strength));
    hot.addColorStop(0.16, rgba(SKY, 0.95 * strength));
    hot.addColorStop(0.36, rgba(WHITE, strength));
    hot.addColorStop(0.55, rgba(colour, 0.8 * strength));
    hot.addColorStop(0.72, rgba(PINK, 0.95 * strength));
    hot.addColorStop(0.88, rgba(WHITE, 0.95 * strength));
    hot.addColorStop(1, rgba(SKY, 0.85 * strength));
    g.lineWidth = 1.8; g.strokeStyle = hot; g.stroke();
  }

  // A bloom of light at every twist (only on the brighter ribbons).
  if (rb.edge < 0.4) return;
  const rad = 84 * (0.55 + 0.45 * amp) * (0.4 + 0.6 * rb.edge);
  for (const [x, y] of crossings) {
    const bloom = g.createRadialGradient(x, y, 0, x, y, rad);
    bloom.addColorStop(0, rgba([214, 224, 255], 0.5 * rb.edge));
    bloom.addColorStop(0.3, rgba([132, 124, 255], 0.2 * rb.edge));
    bloom.addColorStop(1, rgba([132, 124, 255], 0));
    g.fillStyle = bloom;
    g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
}
