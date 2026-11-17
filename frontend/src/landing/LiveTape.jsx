/**
 * LiveTape -- the dark two-track tape in the hero: Vaani's bars on track 01,
 * the visitor's red bars on track 02, captions underneath and the round
 * Cut in button. The loop and the drawing live in useTape.js.
 *
 * Scripted: it never touches the microphone or the network.
 */

import { useRef } from 'react';
import { DEMO } from './landingContent.js';
import useTape from './useTape.js';

// The caption lines: the current speaker in full, the previous one dimmed.
function captionRows(view) {
  const { speakers } = DEMO;
  if (view.reply) {
    return [
      { key: 'u', kind: 'user', who: speakers.user, text: view.user, prev: true },
      { key: 'r', kind: 'vaani', who: speakers.vaani, text: view.reply },
    ];
  }
  if (view.user) {
    return [
      { key: 'v', kind: 'vaani', who: speakers.vaani, text: view.vaani, prev: true },
      { key: 'u', kind: 'user', who: speakers.user, text: view.user },
    ];
  }
  return [{ key: 'v', kind: 'vaani', who: speakers.vaani, text: view.vaani || '…' }];
}

export default function LiveTape({ reducedMotion, leadS, paused, onTogglePause }) {
  const canvasRef = useRef(null);
  const { view, userCut, cutIn } = useTape(canvasRef, { reducedMotion, paused, leadS });

  const { hints } = DEMO;
  let hint = hints.waiting;
  if (reducedMotion) hint = hints.reduced;
  else if (userCut) hint = hints.cutDone;
  else if (view.canCut) hint = hints.canCut;

  return (
    <div className="lp-tape">
      <div className="lp-tape-head lp-mono">
        <span className="lp-tape-title">
          <span className="lp-dot lp-blink" aria-hidden="true" />
          {DEMO.title} &middot; {DEMO.labels[view.phase]}
        </span>
        <span className="lp-tape-meta">
          {DEMO.badge}
          {/* WCAG 2.2.2: motion that runs on its own needs a way to stop it. */}
          {!reducedMotion && (
            <button type="button" className="lp-mono lp-tape-pause" onClick={onTogglePause}>
              {paused ? DEMO.play : DEMO.pause}
            </button>
          )}
        </span>
      </div>

      <div className="lp-tape-body">
        <div className="lp-tape-tracks lp-mono" aria-hidden="true">
          <span>{DEMO.tracks[0]}</span>
          <span className="lp-tape-you">{DEMO.tracks[1]}</span>
        </div>
        {/* Clicking the tape is a mouse shortcut for the Cut in button. It is
            hidden from screen readers and not focusable on purpose: the real,
            keyboard-reachable control is the button below. The scissors
            cursor comes from CSS (--lp-cursor). */}
        <canvas ref={canvasRef} className="lp-tape-canvas" aria-hidden="true" onClick={cutIn} />
      </div>

      <div className="lp-tape-foot">
        <div className="lp-captions">
          {captionRows(view).map((r) => (
            <p key={r.key} className={r.prev ? 'lp-cap lp-cap-prev' : 'lp-cap'}>
              <span className={`lp-mono lp-cap-who lp-cap-${r.kind}`}>{r.who}</span>
              {r.text}
            </p>
          ))}
        </div>
        <div className="lp-cut-wrap">
          <span className="lp-mono lp-cut-hint">{hint}</span>
          {/* aria-disabled (not disabled): the button stays focusable, so a
              keyboard user can reach it and wait for the window to open. */}
          <button
            type="button"
            className="lp-cut"
            aria-disabled={!view.canCut}
            aria-label={DEMO.cutLabel}
            onClick={cutIn}
          >
            <span className="lp-mono">{DEMO.cutButton}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
