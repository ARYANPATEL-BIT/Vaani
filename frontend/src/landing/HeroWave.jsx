/**
 * HeroWave -- the full-width ribbon wave behind the hero, on a <canvas>.
 *
 * One requestAnimationFrame loop advances the scripted demo's clock, eases
 * the wave toward the current phase's amplitude, draws a frame
 * (drawRibbons.js), and tells the parent when the demo text changed.
 *
 * The loop runs only while ALL of these hold: not paused by the visitor,
 * the hero is on screen, the tab is visible, and motion is allowed.
 * Everything it starts is stopped in the effect's cleanup.
 */

import { useEffect, useRef } from 'react';
import { WAVE, DEMO } from './landingContent.js';
import { demoAt, loopTime, flashAt } from './demoScript.js';
import { drawRibbons, stepWave } from './drawRibbons.js';
import { fitCanvas } from './canvasSize.js';

export default function HeroWave({ paused, reducedMotion, leadS, onDemoChange }) {
  const canvasRef = useRef(null);
  // The wave's state lives in a ref, not in React state: it changes 60 times
  // a second and nothing on screen is rendered by React from it. Keeping it
  // in a ref also lets it survive a pause: the effect below restarts on
  // pause/play, and the wave carries on from where it was.
  // elapsed starts negative so the demo waits for the preloader to lift.
  const simRef = useRef({ elapsed: -leadS, amp: 0, ph: 0, demoKey: '' });

  useEffect(() => {
    const canvas = canvasRef.current;
    const sim = simRef.current;

    // Paint the current state once (used every frame, and on resize).
    function render() {
      const fit = fitCanvas(canvas, WAVE.maxDpr, WAVE.maxCanvasPx);
      if (!fit) return;
      const t = loopTime(sim.elapsed);
      drawRibbons(fit.g, fit.w, fit.h, sim.amp, sim.ph, flashAt(t));
    }

    // A ResizeObserver calls us back whenever the canvas changes size (window
    // resize, phone rotation). While the loop runs, the next frame redraws
    // anyway; while it is stopped, we redraw here so the picture is not
    // stretched or blank.
    let raf = 0; // the id of the pending frame request, 0 when stopped
    const resize = new ResizeObserver(() => { if (!raf) render(); });
    resize.observe(canvas);

    if (reducedMotion) {
      // One calm, full frame and no loop at all.
      sim.elapsed = DEMO.stillFrameAt;
      sim.amp = 1;
      sim.ph = 1;
      render();
      return () => resize.disconnect();
    }

    let last = null;     // timestamp of the previous frame
    let onScreen = true; // corrected at once by the IntersectionObserver

    // requestAnimationFrame(cb) asks the browser to call cb just before it
    // paints the next frame (usually 60 times a second) and passes it the
    // current time. Each frame asks for the next one, which makes a loop.
    function frame(now) {
      // Seconds since the last frame, capped: after a stall (a busy main
      // thread, a debugger) the wave continues instead of jumping ahead.
      const dt = last === null ? 0 : Math.min(WAVE.maxStepS, (now - last) / 1000);
      last = now;
      sim.elapsed += dt;
      const demo = demoAt(loopTime(sim.elapsed));
      stepWave(sim, demo.phase, dt, WAVE);
      // Only tell React when the text or phase changed (a few times a
      // second while typing), not on every one of the 60 frames.
      const key = `${demo.phase}|${demo.vaani}|${demo.user}|${demo.reply}`;
      if (key !== sim.demoKey) {
        sim.demoKey = key;
        onDemoChange(demo);
      }
      render();
      raf = requestAnimationFrame(frame);
    }

    function start() {
      if (raf || paused || !onScreen || document.hidden) return;
      last = null; // the first frame after a pause gets dt = 0, no jump
      raf = requestAnimationFrame(frame);
    }
    function stop() {
      // cancelAnimationFrame withdraws the pending request, so frame() is
      // never called again. Without it the loop would keep drawing into a
      // canvas that may no longer be on the page.
      cancelAnimationFrame(raf);
      raf = 0;
    }

    // Pause when the hero is scrolled off screen: drawing what nobody can
    // see costs battery and CPU. IntersectionObserver tells us when the
    // canvas enters or leaves the visible area, without polling on scroll.
    const visible = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      if (onScreen) start(); else stop();
    });
    visible.observe(canvas);

    // Pause when the tab is hidden. Browsers already stop calling rAF in a
    // background tab, but stopping ourselves makes it explicit and resets
    // the clock, so the wave resumes smoothly when the tab comes back.
    function onVisibility() {
      if (document.hidden) stop(); else start();
    }
    document.addEventListener('visibilitychange', onVisibility);

    render(); // show the current frame even if we start paused
    start();

    // The cleanup: React runs this when the component leaves the page, and
    // before re-running the effect (paused or reducedMotion changed). It
    // undoes everything above. Without it, each pause/play or each visit
    // would leave another loop and more listeners running.
    return () => {
      stop();
      visible.disconnect();
      resize.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [paused, reducedMotion, onDemoChange]);

  // aria-hidden: a decorative picture; screen readers skip it. The demo
  // card next to it carries the same story in words.
  return <canvas ref={canvasRef} className="lp-wave-canvas" aria-hidden="true" />;
}
