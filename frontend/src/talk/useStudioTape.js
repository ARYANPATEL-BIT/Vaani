/**
 * useStudioTape -- the Studio tape's one animation loop.
 *
 * requestAnimationFrame (rAF) asks the browser to call a function just
 * before it paints the next frame, about 60 times a second. Each call here:
 *   1. works out the session time (performance.now() minus the start),
 *   2. every TAPE.stepMs, reads the two levels and stores one sample,
 *   3. redraws the canvas (drawStudioTape.js),
 *   4. writes the tape counter's text straight into its DOM node.
 *
 * WHY REFS, NOT STATE: the levels and the counter change every frame. If
 * they were React state, React would re-render the page 60 times a second,
 * on the same main thread that sends mic frames and schedules playback.
 * Instead the loop reads the levels by calling readMic/readPlayback (plain
 * functions that return a number) and writes the counter's text itself.
 * React never re-renders because of the tape.
 *
 * The loop only runs while a session is live and the tab is visible. It is
 * cancelled in the effect's cleanup (session end, unmount, tab hidden).
 * Under reduced motion it still samples, but redraws only twice a second.
 */

import { useEffect, useRef } from 'react';
import { TAPE } from './talkContent.js';
import { createLevelHistory } from './levelHistory.js';
import { drawStudioTape } from './drawStudioTape.js';
import { timecode } from './studioState.js';

const CAPACITY = Math.ceil((TAPE.maxWindowS * 1000) / TAPE.stepMs) + 4;

/**
 * @param {object} refs  canvasRef, counterRef (DOM), startRef (performance.now()
 *                       at session.started, or null), cutsRef (session seconds)
 * @param {object} opts  live, thinking, reducedMotion, readMic, readPlayback
 */
export default function useStudioTape({ canvasRef, counterRef, startRef, cutsRef }, opts) {
  const historyRef = useRef(null);
  if (historyRef.current === null) historyRef.current = createLevelHistory(CAPACITY);
  // The latest options, read by the loop without restarting it. Updated in
  // an effect (after render), not during render.
  const optsRef = useRef(opts);
  useEffect(() => {
    optsRef.current = opts;
  });
  const lastNowRef = useRef(0);

  const { live, reducedMotion } = opts;

  useEffect(() => {
    const canvas = canvasRef.current;
    const history = historyRef.current;
    if (!canvas) return undefined;

    let raf = 0;
    let nextSample = 0;
    let lastDraw = -Infinity;
    let shownCounter = '';

    const frame = (now, dotsLit) => {
      drawStudioTape(canvas, {
        history,
        now,
        cuts: cutsRef.current,
        thinking: optsRef.current.thinking,
        dotsLit,
      });
      const text = timecode(now);
      if (counterRef.current && text !== shownCounter) {
        counterRef.current.textContent = text;
        shownCounter = text;
      }
    };

    // Not live: draw one still frame (the end of the last session, or an
    // empty tape) and redraw it only when the box changes size.
    if (!live || startRef.current === null) {
      frame(lastNowRef.current, 3);
      const ro = new ResizeObserver(() => frame(lastNowRef.current, 3));
      ro.observe(canvas);
      return () => ro.disconnect();
    }

    history.clear(); // a new session starts with a clean tape
    const tick = (ts) => {
      const now = (performance.now() - startRef.current) / 1000;
      lastNowRef.current = now;
      // After a hidden tab or a long stall, skip ahead instead of filling
      // the gap with copies of the current level.
      if (now - nextSample > 1) nextSample = now;
      while (nextSample <= now) {
        const o = optsRef.current;
        history.push(nextSample, o.readPlayback(), o.readMic());
        nextSample += TAPE.stepMs / 1000;
      }
      const reduced = optsRef.current.reducedMotion;
      if (!reduced || ts - lastDraw >= TAPE.reducedMotionMs) {
        frame(now, reduced ? 3 : Math.floor(ts / 250) % 4);
        lastDraw = ts;
      }
      raf = requestAnimationFrame(tick);
    };
    const start = () => {
      if (!raf && document.visibilityState === 'visible') raf = requestAnimationFrame(tick);
    };
    const stop = () => {
      cancelAnimationFrame(raf);
      raf = 0;
    };
    const onVisibility = () => (document.visibilityState === 'visible' ? start() : stop());

    start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      // Cleanup: the session ended, the page unmounted, or reduced motion
      // changed. No frame is requested after this.
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [canvasRef, counterRef, startRef, cutsRef, live, reducedMotion]);
}
