/**
 * Preloader -- वाणी in Tiro Devanagari and a 000-to-100 counter on an ink
 * panel, which then lifts away. LandingPage.jsx decides whether it plays at
 * all (once per browser session, never under reduced motion).
 *
 * The lift is a CSS animation (.lp-pre in landing.css). A timer, not the
 * animation's end event, removes the panel, so the page can never be left
 * covered (and inert) if the animation does not run.
 */

import { useEffect, useState } from 'react';
import { BRAND, PRELOADER } from './landingContent.js';

export default function Preloader({ onDone }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const t0 = performance.now();
    let raf = 0;

    function frame(now) {
      const s = (now - t0) / 1000;
      // React skips the re-render when the number has not changed.
      setCount(Math.min(100, Math.round((100 * s) / PRELOADER.countS)));
      if (s < PRELOADER.countS) raf = requestAnimationFrame(frame);
    }
    // In a hidden tab the browser stops calling frame(); the counter is
    // computed from elapsed time, so it is right again when the tab returns.
    raf = requestAnimationFrame(frame);
    const done = setTimeout(onDone, (PRELOADER.liftStartS + PRELOADER.liftS) * 1000);

    // Cleanup: stop the loop and the timer if the page is left early.
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(done);
    };
  }, [onDone]);

  return (
    // aria-hidden: purely decorative; the page under it is the content.
    <div className="lp-pre" aria-hidden="true">
      <span className="lp-dv lp-pre-mark">{BRAND.hindi}</span>
      <span className="lp-mono lp-pre-label">{PRELOADER.label}</span>
      <span className="lp-mono lp-pre-count">{String(count).padStart(3, '0')} / 100</span>
    </div>
  );
}
