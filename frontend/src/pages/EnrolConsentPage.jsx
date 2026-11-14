/**
 * EnrolConsentPage — Enrolment Consent & Live Challenge Phrase UI.
 *
 * Scope (Week 3 Day 4):
 *  - Step 1: Spoken consent statement display and live recording.
 *  - Step 2: Live challenge phrase display and live recording.
 *    (Challenge phrase is strictly revealed ONLY upon reaching Step 2).
 *  - Strict sequencing: Spoken consent must be successfully recorded before
 *    the challenge phrase is accessible or visible.
 *  - Re-recording support:
 *    - Re-recording consent invalidates challenge to maintain strict sequence.
 *    - Re-recording challenge preserves the consent recording.
 *  - Live AnalyserNode level meter, wall-clock timers, auto-stop at 15s.
 *  - In-browser audio previews (<audio>) for captured recordings.
 *  - Honest representation: Note that server-issued challenge generation
 *    (POST /enrolments) is scheduled for Week 4 backend integration.
 *  - Once both recordings are captured, enables proceeding to /enrol/record.
 */

import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mic,
  MicOff,
  Square,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ArrowRight,
  X,
  Shield,
  AudioLines,
  ChevronLeft,
  Lock,
} from 'lucide-react';
import { usePhraseRecorder } from '../hooks/usePhraseRecorder.js';
import {
  SPOKEN_CONSENT_TEXT,
  CLIENT_CHALLENGE_PHRASE,
} from './enrolConsent.test.js';
import './EnrolConsentPage.css';

/* ── helpers ──────────────────────────────────────────────────────────── */

function formatTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, '0');
  const s = (totalSeconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

/**
 * LevelMeter — Visual meter fed by AnalyserNode RMS.
 * @param {{ level: number, active: boolean }} props
 */
function LevelMeter({ level, active }) {
  const BAR_COUNT = 20;

  return (
    <div
      className="phrase-level-meter"
      role="meter"
      aria-label="Microphone input level"
      aria-valuenow={Math.round(level * 100)}
      aria-valuemin="0"
      aria-valuemax="100"
    >
      {Array.from({ length: BAR_COUNT }, (_, i) => {
        const threshold = i / BAR_COUNT;
        const lit = active && level > threshold;
        const hue = i < 13 ? 142 : i < 17 ? 45 : 0;
        return (
          <div
            key={i}
            className={`phrase-level-bar${lit ? ' lit' : ''}`}
            style={lit ? { background: `hsl(${hue}, 75%, 48%)` } : undefined}
          />
        );
      })}
    </div>
  );
}

export default function EnrolConsentPage() {
  const navigate = useNavigate();

  // Multi-step flow: 'consent' | 'challenge' | 'completed'
  const [step, setStep] = useState('consent');

  // Recorders for Step 1 and Step 2
  const consentRecorder = usePhraseRecorder({ minDuration: 2, maxDuration: 15 });
  const challengeRecorder = usePhraseRecorder({ minDuration: 2, maxDuration: 15 });

  const isConsentComplete = consentRecorder.recordingState === 'completed';
  const isChallengeComplete = challengeRecorder.recordingState === 'completed';

  // Advancing to challenge step
  const handleProceedToChallenge = useCallback(() => {
    if (!isConsentComplete) return;
    setStep('challenge');
  }, [isConsentComplete]);

  // Re-record consent: invalidates challenge to enforce strict sequence
  const handleReRecordConsent = useCallback(() => {
    consentRecorder.reRecord();
    challengeRecorder.reset();
    setStep('consent');
  }, [consentRecorder, challengeRecorder]);

  // Re-record challenge alone
  const handleReRecordChallenge = useCallback(() => {
    challengeRecorder.reRecord();
    setStep('challenge');
  }, [challengeRecorder]);

  // Mark flow complete once challenge recording finishes
  const handleChallengeStop = useCallback(() => {
    challengeRecorder.stopRecording();
  }, [challengeRecorder]);

  // Navigation handlers
  const handleCancel = useCallback(() => {
    navigate('/talk');
  }, [navigate]);

  const handleProceedToReference = useCallback(() => {
    navigate('/enrol/record');
  }, [navigate]);

  return (
    <main className="consent-page" aria-labelledby="enrol-consent-heading">
      <div className="consent-card">
        {/* Header */}
        <div className="consent-header">
          <div className="consent-icon-wrap" aria-hidden="true">
            <Shield size={26} strokeWidth={1.8} />
          </div>
          <div>
            <h1 id="enrol-consent-heading" className="consent-title">
              Enrolment Consent & Verification
            </h1>
            <p className="consent-subtitle">
              Verify your identity with recorded consent and a live challenge phrase.
            </p>
          </div>
        </div>

        {/* Stepper Indicator */}
        <nav className="enrol-stepper" aria-label="Enrolment progress steps">
          <div
            className={`step-item ${step === 'consent' ? 'active' : isConsentComplete ? 'completed' : ''}`}
          >
            <span className="step-num">
              {isConsentComplete ? <CheckCircle2 size={16} /> : '1'}
            </span>
            <span className="step-label">Spoken Consent</span>
          </div>

          <div className="step-divider" aria-hidden="true" />

          <div
            className={`step-item ${step === 'challenge' ? 'active' : isChallengeComplete ? 'completed' : 'locked'}`}
          >
            <span className="step-num">
              {isChallengeComplete ? (
                <CheckCircle2 size={16} />
              ) : step === 'challenge' ? (
                '2'
              ) : (
                <Lock size={14} />
              )}
            </span>
            <span className="step-label">Challenge Phrase</span>
          </div>

          <div className="step-divider" aria-hidden="true" />

          <div className="step-item locked">
            <span className="step-num">3</span>
            <span className="step-label">Reference Audio</span>
          </div>
        </nav>

        {/* ── STEP 1: SPOKEN CONSENT STATEMENT ─────────────────────────────── */}
        <section
          className={`consent-step-card ${step === 'consent' ? 'step-expanded' : 'step-collapsed'}`}
          aria-labelledby="step1-heading"
        >
          <div className="step-card-header">
            <div className="step-card-title-row">
              <span className="step-badge">Step 1</span>
              <h2 id="step1-heading" className="step-card-title">
                Spoken Consent Statement
              </h2>
            </div>
            {isConsentComplete && (
              <span className="step-status-pill success">
                <CheckCircle2 size={14} /> Recorded ({consentRecorder.elapsedSeconds}s)
              </span>
            )}
          </div>

          <p className="step-card-desc">
            To ensure biometric security and compliance (SEC-6), read and record the
            following consent statement aloud.
          </p>

          <div className="phrase-prompt-box">
            <span className="phrase-box-label">Statement to speak:</span>
            <blockquote className="phrase-statement-text">
              &ldquo;{SPOKEN_CONSENT_TEXT}&rdquo;
            </blockquote>
          </div>

          {/* Consent Recording Controls */}
          {step === 'consent' && (
            <div className="recorder-unit">
              {/* Timer & Level Meter */}
              <div className="recorder-metrics-row">
                <div className="recorder-timer">
                  <Clock size={15} aria-hidden="true" />
                  <span>{formatTime(consentRecorder.elapsedSeconds)}</span>
                  {consentRecorder.recordingState === 'recording' && (
                    <span className="max-tag">/ 00:15 max</span>
                  )}
                </div>

                <div className="recorder-meter-wrap">
                  <AudioLines size={14} aria-hidden="true" />
                  <LevelMeter
                    level={consentRecorder.level}
                    active={consentRecorder.recordingState === 'recording'}
                  />
                </div>
              </div>

              {/* Feedback messages */}
              {consentRecorder.recordingState === 'too_short' && (
                <div className="record-feedback record-feedback-warning" role="alert">
                  <AlertTriangle size={16} aria-hidden="true" />
                  <div>
                    <strong>Recording too short.</strong> Please speak the full consent
                    statement (minimum 2 seconds).
                  </div>
                </div>
              )}

              {consentRecorder.recordingState === 'failed' &&
                consentRecorder.errorMessage && (
                  <div className="record-feedback record-feedback-error" role="alert">
                    <MicOff size={16} aria-hidden="true" />
                    <div>
                      <strong>Could not record:</strong> {consentRecorder.errorMessage}
                    </div>
                  </div>
                )}

              {isConsentComplete && (
                <div className="record-feedback record-feedback-success" role="status">
                  <CheckCircle2 size={16} aria-hidden="true" />
                  <div>
                    <strong>Consent recorded successfully.</strong> You can review the
                    audio below or proceed to the challenge phrase.
                  </div>
                </div>
              )}

              {/* Audio preview */}
              {isConsentComplete && consentRecorder.recordingUrl && (
                <div className="record-preview-section">
                  <p className="record-preview-label">Preview your consent recording:</p>
                  <audio
                    id="consent-preview-audio"
                    className="record-preview-audio"
                    src={consentRecorder.recordingUrl}
                    controls
                    aria-label="Preview of spoken consent recording"
                  />
                </div>
              )}

              {/* Action Buttons for Step 1 */}
              <div className="recorder-actions">
                {consentRecorder.recordingState !== 'recording' &&
                  !isConsentComplete && (
                    <button
                      id="consent-record-start-btn"
                      type="button"
                      className="consent-btn consent-btn-primary"
                      onClick={consentRecorder.startRecording}
                      disabled={consentRecorder.recordingState === 'requesting'}
                      aria-label="Start recording consent statement"
                    >
                      <Mic size={16} />
                      {consentRecorder.recordingState === 'requesting'
                        ? 'Requesting mic…'
                        : 'Start Recording'}
                    </button>
                  )}

                {consentRecorder.recordingState === 'recording' && (
                  <button
                    id="consent-record-stop-btn"
                    type="button"
                    className="consent-btn consent-btn-stop"
                    onClick={consentRecorder.stopRecording}
                    aria-label="Stop recording consent statement"
                  >
                    <Square size={16} />
                    Stop Recording
                  </button>
                )}

                {isConsentComplete && (
                  <>
                    <button
                      id="consent-rerecord-btn"
                      type="button"
                      className="consent-btn consent-btn-secondary"
                      onClick={handleReRecordConsent}
                      aria-label="Re-record consent statement"
                    >
                      <RefreshCw size={15} />
                      Record Again
                    </button>
                    <button
                      id="consent-proceed-btn"
                      type="button"
                      className="consent-btn consent-btn-primary"
                      onClick={handleProceedToChallenge}
                      aria-label="Proceed to challenge phrase step"
                    >
                      Next: Challenge Phrase
                      <ArrowRight size={16} />
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </section>

        {/* ── STEP 2: LIVE CHALLENGE PHRASE ─────────────────────────────────── */}
        {/* Strict visibility guard: ONLY rendered when step !== 'consent' */}
        {step !== 'consent' && (
          <section
            className="consent-step-card step-expanded"
            aria-labelledby="step2-heading"
          >
            <div className="step-card-header">
              <div className="step-card-title-row">
                <span className="step-badge">Step 2</span>
                <h2 id="step2-heading" className="step-card-title">
                  Live Challenge Phrase
                </h2>
              </div>
              {isChallengeComplete && (
                <span className="step-status-pill success">
                  <CheckCircle2 size={14} /> Recorded ({challengeRecorder.elapsedSeconds}s)
                </span>
              )}
            </div>

            <p className="step-card-desc">
              Speak the live challenge phrase below to prove liveness and prevent replay
              attacks.
            </p>

            {/* Honest Week 4 blocker / client phrase notice */}
            <div className="challenge-notice-banner" role="note">
              <span className="notice-tag">Client Challenge Phrase</span>
              <p className="notice-text">
                Live verification phrase. Note: Server-issued challenge generation
                (<code>POST /enrolments</code>) is scheduled for Week 4 backend integration.
              </p>
            </div>

            {/* Revealed Challenge Phrase */}
            <div className="phrase-prompt-box challenge-box">
              <span className="phrase-box-label">Challenge phrase to speak:</span>
              <blockquote className="phrase-statement-text challenge-text">
                &ldquo;{CLIENT_CHALLENGE_PHRASE}&rdquo;
              </blockquote>
            </div>

            {/* Challenge Recording Controls */}
            <div className="recorder-unit">
              <div className="recorder-metrics-row">
                <div className="recorder-timer">
                  <Clock size={15} aria-hidden="true" />
                  <span>{formatTime(challengeRecorder.elapsedSeconds)}</span>
                  {challengeRecorder.recordingState === 'recording' && (
                    <span className="max-tag">/ 00:15 max</span>
                  )}
                </div>

                <div className="recorder-meter-wrap">
                  <AudioLines size={14} aria-hidden="true" />
                  <LevelMeter
                    level={challengeRecorder.level}
                    active={challengeRecorder.recordingState === 'recording'}
                  />
                </div>
              </div>

              {challengeRecorder.recordingState === 'too_short' && (
                <div className="record-feedback record-feedback-warning" role="alert">
                  <AlertTriangle size={16} aria-hidden="true" />
                  <div>
                    <strong>Recording too short.</strong> Please speak the full challenge
                    phrase (minimum 2 seconds).
                  </div>
                </div>
              )}

              {challengeRecorder.recordingState === 'failed' &&
                challengeRecorder.errorMessage && (
                  <div className="record-feedback record-feedback-error" role="alert">
                    <MicOff size={16} aria-hidden="true" />
                    <div>
                      <strong>Could not record:</strong> {challengeRecorder.errorMessage}
                    </div>
                  </div>
                )}

              {isChallengeComplete && (
                <div className="record-feedback record-feedback-success" role="status">
                  <CheckCircle2 size={16} aria-hidden="true" />
                  <div>
                    <strong>Challenge recorded successfully.</strong> Both recordings are
                    captured.
                  </div>
                </div>
              )}

              {/* Audio preview for challenge */}
              {isChallengeComplete && challengeRecorder.recordingUrl && (
                <div className="record-preview-section">
                  <p className="record-preview-label">Preview your challenge recording:</p>
                  <audio
                    id="challenge-preview-audio"
                    className="record-preview-audio"
                    src={challengeRecorder.recordingUrl}
                    controls
                    aria-label="Preview of live challenge phrase recording"
                  />
                </div>
              )}

              {/* Action Buttons for Step 2 */}
              <div className="recorder-actions">
                {challengeRecorder.recordingState !== 'recording' &&
                  !isChallengeComplete && (
                    <>
                      <button
                        id="back-to-consent-btn"
                        type="button"
                        className="consent-btn consent-btn-secondary"
                        onClick={handleReRecordConsent}
                        aria-label="Go back and re-record consent statement"
                      >
                        <ChevronLeft size={16} />
                        Re-record Consent
                      </button>
                      <button
                        id="challenge-record-start-btn"
                        type="button"
                        className="consent-btn consent-btn-primary"
                        onClick={challengeRecorder.startRecording}
                        disabled={challengeRecorder.recordingState === 'requesting'}
                        aria-label="Start recording challenge phrase"
                      >
                        <Mic size={16} />
                        {challengeRecorder.recordingState === 'requesting'
                          ? 'Requesting mic…'
                          : 'Record Challenge'}
                      </button>
                    </>
                  )}

                {challengeRecorder.recordingState === 'recording' && (
                  <button
                    id="challenge-record-stop-btn"
                    type="button"
                    className="consent-btn consent-btn-stop"
                    onClick={handleChallengeStop}
                    aria-label="Stop recording challenge phrase"
                  >
                    <Square size={16} />
                    Stop Recording
                  </button>
                )}

                {isChallengeComplete && (
                  <>
                    <button
                      id="challenge-rerecord-btn"
                      type="button"
                      className="consent-btn consent-btn-secondary"
                      onClick={handleReRecordChallenge}
                      aria-label="Re-record challenge phrase"
                    >
                      <RefreshCw size={15} />
                      Record Challenge Again
                    </button>
                    <button
                      id="re-record-consent-btn"
                      type="button"
                      className="consent-btn consent-btn-secondary"
                      onClick={handleReRecordConsent}
                      aria-label="Start over with consent recording"
                    >
                      <ChevronLeft size={15} />
                      Re-record Consent
                    </button>
                  </>
                )}
              </div>
            </div>
          </section>
        )}

        {/* ── FINAL ACTIONS ─────────────────────────────────────────────────── */}
        <div className="consent-bottom-actions">
          <button
            id="enrol-cancel-btn"
            type="button"
            className="consent-btn consent-btn-secondary"
            onClick={handleCancel}
            aria-label="Cancel enrolment and return to conversation"
          >
            <X size={16} />
            Cancel
          </button>

          <button
            id="enrol-proceed-reference-btn"
            type="button"
            className="consent-btn consent-btn-primary"
            onClick={handleProceedToReference}
            disabled={!isConsentComplete || !isChallengeComplete}
            aria-disabled={!isConsentComplete || !isChallengeComplete}
            aria-label="Continue to 30-60 second reference voice recording"
          >
            Continue to Reference Voice
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </main>
  );
}
