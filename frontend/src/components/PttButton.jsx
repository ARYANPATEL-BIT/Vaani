/**
 * PttButton — the push-to-talk control (docs/contracts.md §2.8).
 *
 * Shown by ConversationPage only in a session the server confirmed as "ptt".
 * Two ways to talk, both ending in the same onSpeak / onStop:
 * - the button TOGGLES: click Speak, talk, click Stop;
 * - the Space bar is HOLD-TO-TALK: key down starts, key up stops.
 *
 * Space details:
 * - A held key repeats its keydown many times a second (auto-repeat).
 *   Those repeats carry `event.repeat === true` and are ignored, so one hold
 *   is one press. (The press state in pttPress.js ignores them too.)
 * - Nothing happens while the user is typing in a text field.
 * - preventDefault on both keydown and keyup: Space would otherwise scroll
 *   the page, or "click" whichever button has focus (often this one, right
 *   after it was clicked), which would toggle the press a second time.
 */

import { useEffect } from 'react';

/** True if the key event is aimed at a place the user types into. */
function isTypingTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}

export function PttButton({ pressState = 'idle', onSpeak, onStop }) {
  useEffect(() => {
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
  }, [onSpeak, onStop]);

  const holding = pressState === 'holding';
  // Stopping lasts until the worklet's last frame is sent: a few ms, at
  // most PTT_END_FALLBACK_MS. A click then would be ignored anyway.
  const stopping = pressState === 'stopping';

  return (
    <button
      type="button"
      id="ptt-btn"
      className={`control-btn ptt-btn${holding ? ' ptt-holding' : ''}`}
      onClick={holding ? onStop : onSpeak}
      disabled={stopping}
      aria-pressed={holding}
      aria-label={holding ? 'Stop talking' : 'Start talking'}
    >
      <div className="btn-icon-wrapper ptt-icon-wrapper">
        {holding ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15a3 3 0 01-3-3V4.5a3 3 0 116 0v7.5a3 3 0 01-3 3z" />
          </svg>
        )}
      </div>
      <span className="btn-label">{holding ? 'Stop' : 'Speak'}</span>
      <span className="ptt-hint">or hold Space</span>
    </button>
  );
}

export default PttButton;
