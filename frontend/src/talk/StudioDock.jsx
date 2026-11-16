/**
 * StudioDock -- the bottom bar: tape counter, the session buttons, and the
 * keyboard hints.
 *
 * Buttons, by situation:
 *   no session          -> Talk (connects; disabled while connecting)
 *   hands-free session  -> End, as the big red button (there is no Mute)
 *   push-to-talk        -> End beside a big Talk / Stop
 *   phone, always       -> also Script, which opens the full transcript
 *
 * Keys (never while typing in a text field):
 *   Space -> push-to-talk only: hold to talk. Same rules as the old
 *            PttButton: auto-repeat ignored, preventDefault on down and up.
 *   Esc   -> ends the session, unless a dialog is open (Esc closes that).
 *
 * The counter's text is written by useStudioTape.js through counterRef,
 * not by React (it changes every frame).
 */

import { useEffect } from 'react';
import { HINTS, TEXT } from './talkContent.js';

function isTypingTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

export default function StudioDock({
  isCapturing, isConnected, isTransitioning, sessionMode, pressState,
  onConnect, onDisconnect, onSpeak, onStop, onOpenScript, counterRef,
}) {
  const ptt = isConnected && sessionMode === 'ptt';

  // Space: hold-to-talk, only in a push-to-talk session.
  useEffect(() => {
    if (!ptt) return undefined;
    const onKeyDown = (event) => {
      if (event.code !== 'Space' || isTypingTarget(event.target)) return;
      event.preventDefault();
      if (event.repeat) return; // auto-repeat: still the same hold
      onSpeak();
    };
    const onKeyUp = (event) => {
      if (event.code !== 'Space' || isTypingTarget(event.target)) return;
      event.preventDefault();
      onStop();
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [ptt, onSpeak, onStop]);

  // Esc: end the session.
  useEffect(() => {
    if (!isCapturing) return undefined;
    const onKeyDown = (event) => {
      if (event.key !== 'Escape' || isTypingTarget(event.target)) return;
      if (document.querySelector('dialog[open]')) return; // the dialog takes Esc
      onDisconnect();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isCapturing, onDisconnect]);

  const holding = pressState === 'holding';
  const hints = !isCapturing ? HINTS.idle : ptt ? HINTS.ptt : HINTS.vad;

  return (
    <footer className="tk-dock">
      <div className="tk-counter tk-wide-only">
        <span className="tk-mono tk-small">{TEXT.counter}</span>
        <span className="tk-cd tk-counter-num" ref={counterRef} aria-hidden="true">00:00.00</span>
      </div>

      <div className="tk-dock-buttons">
        {!isCapturing && (
          <button type="button" id="connect-btn" className="tk-mono tk-big"
            onClick={onConnect} disabled={isTransitioning} aria-label={TEXT.aria.connect}>
            <span className="tk-big-dot" aria-hidden="true" />
            {isTransitioning ? TEXT.tuning : TEXT.talk}
          </button>
        )}
        {isCapturing && (
          <button type="button" id="disconnect-btn" className={ptt ? 'tk-mono tk-ghost' : 'tk-mono tk-big'}
            onClick={onDisconnect} aria-label={TEXT.aria.end}>
            <span aria-hidden="true">■ </span>{TEXT.end}
          </button>
        )}
        {ptt && (
          <button type="button" id="ptt-btn" className={holding ? 'tk-mono tk-big tk-big-on' : 'tk-mono tk-big'}
            onClick={holding ? onStop : onSpeak} disabled={pressState === 'stopping'}
            aria-pressed={holding} aria-label={holding ? TEXT.aria.stopTalking : TEXT.aria.speak}>
            <span className="tk-big-dot" aria-hidden="true" />
            {holding ? TEXT.stop : TEXT.talk}
          </button>
        )}
        <button type="button" className="tk-mono tk-ghost tk-phone-only"
          aria-haspopup="dialog" aria-label={TEXT.aria.showScript} onClick={onOpenScript}>
          {TEXT.scriptButton}
        </button>
      </div>

      <p className="tk-mono tk-small tk-dock-hints tk-wide-only">
        {hints[0]}<br />{hints[1]}
      </p>
    </footer>
  );
}
