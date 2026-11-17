/**
 * useTape -- runs the scripted tape demo: the clock, the cut, the canvas.
 *
 * It owns one small clock object (in a ref, so changing it does not
 * re-render): `t` (seconds into the loop), `cut` (when the cut happens),
 * `lead` (seconds still to wait for the loader) and `last` (the previous
 * frame's timestamp). Every animation frame it moves `t` forward, draws the
 * canvas, and hands the caption text to React only when it changed.
 *
 * Returns { view, userCut, cutIn }: the captions/phase to show, whether the
 * visitor has cut in during this loop, and the Cut in handler.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { DEMO, TAPE } from './landingContent.js';
import { demoAt, canCutAt, loopEnd } from './demoScript.js';
import { drawTape } from './drawTape.js';

const TL = DEMO.timeline;

// What reduced motion shows: one finished exchange, Cut in disabled.
const STILL = { ...demoAt(DEMO.stillFrameAt), canCut: false };

function viewAt(clock) {
  return {
    ...demoAt(clock.t, clock.cut),
    canCut: clock.lead <= 0 && canCutAt(clock.t, clock.cut),
  };
}

const sameView = (a, b) =>
  a.vaani === b.vaani && a.user === b.user && a.reply === b.reply &&
  a.phase === b.phase && a.canCut === b.canCut;

export default function useTape(canvasRef, { reducedMotion, paused, leadS }) {
  const clock = useRef({ t: 0, cut: TL.defaultCut, lead: leadS, last: null });
  // The first frame: t = 0 with the default cut (the same values as the
  // clock above), built from those values, not by reading the ref in render.
  const [view, setView] = useState(() => viewAt({ t: 0, cut: TL.defaultCut, lead: leadS }));
  const [userCut, setUserCut] = useState(false);

  // Draw the current moment and pass the text to React. The functional
  // setView returns the old object when nothing changed, so React skips the
  // re-render: captions re-render a few times a second, not 60.
  const publish = useCallback(() => {
    const c = clock.current;
    const next = viewAt(c);
    setView((prev) => (sameView(prev, next) ? prev : next));
    if (canvasRef.current) drawTape(canvasRef.current, c.t, c.cut, next.phase);
  }, [canvasRef]);

  useEffect(() => {
    const canvas = canvasRef.current;

    if (reducedMotion) {
      // One still frame, no loop. Redraw it when the canvas is resized
      // (resizing a canvas wipes it) and once the mono font has loaded
      // (the first draw may have used a fallback font for the timecodes).
      let alive = true;
      const drawStill = () => drawTape(canvas, DEMO.stillFrameAt, TL.defaultCut, STILL.phase);
      const ro = new ResizeObserver(drawStill);
      ro.observe(canvas);
      document.fonts.ready.then(() => { if (alive) drawStill(); });
      return () => { alive = false; ro.disconnect(); };
    }

    let raf = 0;              // non-zero while a frame is requested
    let visible = !document.hidden;
    let onScreen = true;

    function frame(now) {
      const c = clock.current;
      // Time since the last frame, capped: after a stall the demo moves on
      // by at most maxStepS instead of jumping ahead (or past the cut).
      const dt = c.last === null ? 0 : Math.min(TAPE.maxStepS, (now - c.last) / 1000);
      c.last = now;
      if (c.lead > 0) {
        c.lead -= dt; // the loader still covers the hero: wait
      } else {
        c.t += dt;
        if (c.t >= loopEnd(c.cut)) { // loop over: start again with the default cut
          c.t = 0;
          c.cut = TL.defaultCut;
          setUserCut(false);
        }
      }
      publish();
      raf = requestAnimationFrame(frame);
    }

    // Start or stop the loop so it runs only when all three are true: not
    // paused by the visitor, the tab is visible, the tape is on screen.
    // Drawing what nobody can see only burns battery.
    function sync() {
      const shouldRun = !paused && visible && onScreen;
      if (shouldRun && !raf) {
        clock.current.last = null; // resume from where it stopped, no jump
        raf = requestAnimationFrame(frame);
      } else if (!shouldRun && raf) {
        cancelAnimationFrame(raf);
        raf = 0;
      }
    }

    // visibilitychange fires when the tab is hidden or shown again.
    const onVisibility = () => { visible = !document.hidden; sync(); };
    document.addEventListener('visibilitychange', onVisibility);
    // IntersectionObserver tells us when the canvas scrolls out of / into view.
    const io = new IntersectionObserver(([entry]) => { onScreen = entry.isIntersecting; sync(); });
    io.observe(canvas);
    // Paused or off screen, the loop is not drawing, so redraw on resize.
    const ro = new ResizeObserver(() => { if (!raf) publish(); });
    ro.observe(canvas);
    sync();

    // Cleanup runs when the page is left or paused/reducedMotion change:
    // cancel the pending frame and remove every observer and listener, so no
    // loop keeps drawing into a canvas that is gone.
    return () => {
      if (raf) cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [canvasRef, reducedMotion, paused, publish]);

  // Cut in: move the cut to "now". Vaani's sentence freezes at exactly the
  // characters typed so far (demoAt), and everything after re-times from here.
  // Ignored outside the allowed window, so a double click cannot cut twice.
  const cutIn = useCallback(() => {
    const c = clock.current;
    if (reducedMotion || c.lead > 0 || !canCutAt(c.t, c.cut)) return;
    c.cut = c.t;
    setUserCut(true);
    publish(); // show it at once, even if the loop is paused
  }, [reducedMotion, publish]);

  return { view: reducedMotion ? STILL : view, userCut, cutIn };
}
