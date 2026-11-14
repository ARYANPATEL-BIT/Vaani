/**
 * Preloader -- a small waveform and a 000-to-100 counter over the page,
 * which then lifts away. LandingPage.jsx decides whether it plays at all
 * (once per browser session, never under reduced motion).
 *
 * The lift-away is a CSS animation (.lp-pre in landing.css). A timer, not
 * the animation's end event, removes the overlay, so the page can never be
 * left covered (and inert) if the animation does not run.
 */

import { useEffect, useRef, useState } from 'react';
import { ACCENT, PRELOADER } from './landingContent.js';
import { fitCanvas } from './canvasSize.js';

const BARS = 61;
const ACCENT_BARS = [25, 36]; // two bars drawn in the accent colour

function drawBars(canvas, seconds) {
  const fit = fitCanvas(canvas, 2);
  if (!fit) return;
  const { g, w, h } = fit;
  g.clearRect(0, 0, w, h);
  const step = w / BARS;
  for (let i = 0; i < BARS; i++) {
    const d = (i - 30) / 30;
    const envelope = Math.exp(-d * d * 5); // tall in the middle, short at the ends
    const wobble = Math.abs(Math.sin(i * 0.9 + seconds * 6 + Math.sin(i * 0.37) * 2));
    const bh = 3 + envelope * (h - 12) * (0.3 + 0.7 * wobble);
    g.fillStyle = ACCENT_BARS.includes(i) ? ACCENT : '#FFFFFF';
    g.fillRect(i * step + step * 0.25, h / 2 - bh / 2, Math.max(2, step * 0.45), bh);
  }
}

export default function Preloader({ onDone }) {
  const canvasRef = useRef(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    const t0 = performance.now();
    const totalS = PRELOADER.fadeStartS + PRELOADER.fadeS;
    let raf = 0;

    function frame(now) {
      const s = (now - t0) / 1000;
      // React skips the re-render when the number has not changed.
      setCount(Math.min(100, Math.round((100 * s) / PRELOADER.countS)));
      drawBars(canvas, s);
      if (s < totalS) raf = requestAnimationFrame(frame);
    }
    // In a hidden tab the browser stops calling frame(); the counter is
    // computed from elapsed time, so it is right again when the tab returns.
    raf = requestAnimationFrame(frame);
    const done = setTimeout(onDone, totalS * 1000);

    // Cleanup: stop the loop and the timer if the page is left early.
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(done);
    };
  }, [onDone]);

  return (
    // aria-hidden: purely decorative; the page under it is the content.
    <div className="lp-pre" aria-hidden="true">
      <canvas ref={canvasRef} className="lp-pre-canvas" />
      <span className="lp-pre-label">
        <span className="lp-dot" />
        {PRELOADER.label}
      </span>
      <span className="lp-pre-count lp-serif">{String(count).padStart(3, '0')}</span>
    </div>
  );
}
