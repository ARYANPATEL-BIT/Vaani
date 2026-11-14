/**
 * EnrolVerifyPage — /enrol/verify (Week 4 Tuesday).
 *
 * After validation accepts the reference recording, the operator hears a
 * test sentence spoken in the cloned voice and decides:
 *   "Yes, use this voice"  — enabled only after the sample played to the end;
 *                            the voice is shown as active only after the
 *                            server confirms the approval.
 *   "No, record again"     — back to /enrol/record, which starts fresh.
 *
 * The enrolment id arrives in router state from EnrolValidationPage.
 * Demo without a backend: /enrol/verify?demo=ok | load-error | approve-error
 * (see enrol/verifyDemo.js).
 *
 * All state logic lives in enrol/verifyState.js; the network, cancellation
 * and <audio> wiring in hooks/useVoiceVerify.js. This file only draws.
 */

import { useLocation, useNavigate } from 'react-router-dom';
import {
  Loader, Play, Square, CheckCircle2, RotateCcw, AlertTriangle, Home,
} from 'lucide-react';
import { useVoiceVerify } from '../hooks/useVoiceVerify.js';
import { canApprove, canPlay } from '../enrol/verifyState.js';
import { DEMO_MODES } from '../enrol/verifyDemo.js';
import './EnrolVerifyPage.css';

const STATUS_TEXT = {
  loading: 'Rendering the test sentence in your cloned voice…',
  ready: 'Listen to the whole sample, then decide.',
  playing: 'Playing…',
  error: 'No sample to play.',
  approving: 'Saving your approval…',
  approved: 'Voice approved.',
};

export default function EnrolVerifyPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const enrolmentId = location.state?.enrolmentId ?? null;
  const demoParam = new URLSearchParams(location.search).get('demo');
  const demoMode = DEMO_MODES.includes(demoParam) ? demoParam : null;

  const {
    state, hasTarget, audioRef, togglePlay, onEnded, onAudioError, approve, retryLoad,
  } = useVoiceVerify(enrolmentId, demoMode);
  const { status, sampleUrl, hasPlayed, error } = state;

  // Leaving this page unmounts it: the hook aborts any request in flight and
  // frees the sample. /enrol/record mounts with a fresh, empty recorder.
  const recordAgain = () => navigate('/enrol/record');

  return (
    <main className="verify-page" aria-labelledby="verify-title">
      <section className="verify-card">
        <h1 id="verify-title" className="verify-title">Check your cloned voice</h1>
        {demoMode && (
          <p className="verify-demo-note">Demo mode ({demoMode}): no server is contacted, the sample is a test tone.</p>
        )}

        {status === 'approved' ? (
          <div className="verify-approved" role="status">
            <CheckCircle2 size={40} strokeWidth={1.8} aria-hidden="true" />
            <h2>Your voice is active</h2>
            <p>{demoMode ? 'Demo only: nothing was saved.' : 'The server confirmed your approval.'}</p>
            <button type="button" className="verify-btn verify-btn-primary" onClick={() => navigate('/')}>
              <Home size={16} strokeWidth={2} aria-hidden="true" />
              Start using Vaani
            </button>
          </div>
        ) : (
          <>
            {/* aria-live: screen readers announce the status line when it changes */}
            <p className="verify-status" aria-live="polite">
              {status === 'loading' && <Loader size={16} className="verify-spinner" aria-hidden="true" />}
              {STATUS_TEXT[status]}
            </p>

            {/* No native controls: our Play button is the only way to play,
                so every play goes through the state machine. */}
            {sampleUrl && (
              <audio ref={audioRef} src={sampleUrl} onEnded={onEnded} onError={onAudioError} preload="auto" />
            )}

            <button
              type="button"
              className="verify-btn verify-play-btn"
              onClick={togglePlay}
              disabled={!canPlay(state)}
            >
              {status === 'playing'
                ? <><Square size={16} strokeWidth={2} aria-hidden="true" /> Stop</>
                : <><Play size={16} strokeWidth={2} aria-hidden="true" /> {hasPlayed ? 'Play again' : 'Play test sentence'}</>}
            </button>

            {error && (
              <div className="verify-error" role="alert">
                <AlertTriangle size={18} strokeWidth={2} aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            <div className="verify-actions">
              <button
                type="button"
                className="verify-btn verify-btn-primary"
                onClick={approve}
                disabled={!canApprove(state)}
                title={hasPlayed ? undefined : 'Play the sample to the end first'}
              >
                {status === 'approving'
                  ? <Loader size={16} className="verify-spinner" aria-hidden="true" />
                  : <CheckCircle2 size={16} strokeWidth={2} aria-hidden="true" />}
                Yes, use this voice
              </button>
              <button
                type="button"
                className="verify-btn verify-btn-secondary"
                onClick={recordAgain}
                disabled={status === 'approving'}
              >
                <RotateCcw size={16} strokeWidth={2} aria-hidden="true" />
                No, record again
              </button>
            </div>

            {status === 'error' && hasTarget && (
              <button type="button" className="verify-btn verify-btn-secondary" onClick={retryLoad}>
                Try loading the sample again
              </button>
            )}
          </>
        )}
      </section>
    </main>
  );
}
