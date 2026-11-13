/**
 * EnrolValidationPage — Enrolment validation feedback screen for Vaani.
 *
 * Implements Week 3 Day 5 functionality:
 * - Displays specific, actionable user-facing messages for each validation rejection reason code:
 *     1. TOO_SHORT (DATA-2: Duration < 30 s)
 *     2. TOO_LONG (DATA-2: Duration > 60 s)
 *     3. TOO_QUIET (DATA-2: Amplitude below SNR floor)
 *     4. CLIPPING (DATA-1: Waveform distortion / dynamic range peak)
 *     5. EXCESSIVE_SILENCE (DATA-2: Pauses and silence gaps)
 *     6. INSUFFICIENT_SPEECH (DATA-2: No vocal speech detected)
 *     7. LOW_SNR (DATA-2: Excessive ambient noise or echo)
 *     8. UNSUPPORTED_FORMAT (DATA-1: 16 kHz mono 16-bit PCM mismatch)
 *     9. CONSENT_MISSING (TEST-007: Spoken consent not recorded)
 *     10. CHALLENGE_MISMATCH (PERF-9: Speaker similarity < 0.80)
 *     11. UNKNOWN_REJECTION_REASON (Resilient fallback for unmapped codes)
 * - Clear recovery pathways:
 *     - "Record Again" returns to /enrol/record with fresh state.
 *     - "Return to Consent" returns to /enrol if consent/challenge failed.
 *
 * Week 4 Day 1 addition — API result display:
 * - Reads real API result from router state: { accepted: true } or
 *   { rejected: true, reason: '<code>' }.
 * - Shows a dedicated "Enrolment Accepted" success view when accepted.
 * - Shows rejection feedback with real server reason code when rejected.
 * - Interactive reason preview switcher retained for direct verification.
 */

import { useState, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Clock,
  Mic,
  Volume2,
  VolumeX,
  AudioLines,
  ShieldAlert,
  UserCheck,
  ChevronLeft,
  RotateCcw,
  Info,
  CheckCircle2,
  FileQuestion,
  ShieldCheck,
  Home,
} from 'lucide-react';
import {
  REJECTION_REASONS,
  REJECTION_FEEDBACK_DETAILS,
  parseValidationFeedback,
} from '../enrol/enrolValidationContracts.js';
import './EnrolValidationPage.css';

/**
 * Static component to render the category icon without recreating component definitions.
 */
function CategoryIcon({ category, code }) {
  if (code === REJECTION_REASONS.TOO_SHORT || code === REJECTION_REASONS.TOO_LONG) {
    return <Clock size={24} strokeWidth={2} className="rejection-icon" />;
  }
  if (code === REJECTION_REASONS.TOO_QUIET) {
    return <VolumeX size={24} strokeWidth={2} className="rejection-icon" />;
  }
  if (code === REJECTION_REASONS.CLIPPING) {
    return <Volume2 size={24} strokeWidth={2} className="rejection-icon" />;
  }
  if (code === REJECTION_REASONS.EXCESSIVE_SILENCE) {
    return <AudioLines size={24} strokeWidth={2} className="rejection-icon" />;
  }
  if (code === REJECTION_REASONS.INSUFFICIENT_SPEECH) {
    return <Mic size={24} strokeWidth={2} className="rejection-icon" />;
  }
  if (code === REJECTION_REASONS.LOW_SNR) {
    return <AudioLines size={24} strokeWidth={2} className="rejection-icon" />;
  }
  if (code === REJECTION_REASONS.CONSENT_MISSING || code === REJECTION_REASONS.CHALLENGE_MISMATCH) {
    return <ShieldAlert size={24} strokeWidth={2} className="rejection-icon" />;
  }
  if (category === 'format') {
    return <Info size={24} strokeWidth={2} className="rejection-icon" />;
  }
  return <FileQuestion size={24} strokeWidth={2} className="rejection-icon" />;
}

/**
 * AcceptedView — shown when the server validated the recording successfully.
 */
function AcceptedView({ onGoHome }) {
  return (
    <div className="validation-accepted-box" role="status" data-testid="accepted-box">
      <div className="accepted-icon-wrap" aria-hidden="true">
        <ShieldCheck size={48} strokeWidth={1.6} />
      </div>
      <h2 className="accepted-title" data-testid="accepted-title">
        Voice Enrolment Accepted
      </h2>
      <p className="accepted-message" data-testid="accepted-message">
        Your reference voice recording has been validated and accepted. Your voice
        profile is now active on Vaani.
      </p>
      <button
        id="validation-go-home-btn"
        type="button"
        className="validation-btn validation-btn-primary"
        onClick={onGoHome}
        aria-label="Return to the conversation screen"
      >
        <Home size={16} strokeWidth={2} />
        Start Using Vaani
      </button>
    </div>
  );
}

export default function EnrolValidationPage() {
  const location = useLocation();
  const navigate = useNavigate();

  // ── Read navigation state ─────────────────────────────────────────────
  // Week 4 Day 1: EnrolRecordPage now passes real API results:
  //   { accepted: true }                          — server accepted
  //   { rejected: true, reason: '<CODE>' }        — server rejected with code
  //   { reason: '<CODE>' }                        — client pre-validation (legacy)
  //   { error: <feedback-object> }                — client pre-validation error object

  const navState = useMemo(() => location.state || {}, [location.state]);
  const isAccepted = navState.accepted === true;

  // Determine the initial rejection reason code for the switcher
  const queryParams = new URLSearchParams(location.search);
  const initialReasonParam = queryParams.get('reason') || queryParams.get('code');

  const initialCode = useMemo(() => {
    if (isAccepted) return REJECTION_REASONS.TOO_SHORT; // switcher default; won't show
    // Real rejection from API
    if (navState.rejected && navState.reason) {
      return parseValidationFeedback(navState.reason).canonicalCode;
    }
    // Client pre-validation error object
    if (navState.error) {
      return parseValidationFeedback(navState.error).canonicalCode;
    }
    // Reason string from legacy navigation or query param
    const rawReason = navState.reason || initialReasonParam;
    if (rawReason) {
      return parseValidationFeedback(rawReason).canonicalCode;
    }
    // Default
    return REJECTION_REASONS.TOO_SHORT;
  }, [isAccepted, navState, initialReasonParam]);

  // Selected code for the interactive verification switcher
  const [selectedCode, setSelectedCode] = useState(initialCode);

  const feedback = useMemo(() => {
    return parseValidationFeedback(selectedCode);
  }, [selectedCode]);

  const handleRecordAgain = () => {
    navigate('/enrol/record');
  };

  const handleReturnToConsent = () => {
    navigate('/enrol');
  };

  const handleBack = () => {
    if (isAccepted) {
      navigate('/');
    } else if (feedback.action === 'consent') {
      navigate('/enrol');
    } else {
      navigate('/enrol/record');
    }
  };

  const handleGoHome = () => {
    navigate('/');
  };

  return (
    <main className="validation-page" aria-labelledby="validation-title">
      {/* Back button */}
      <button
        id="validation-back-btn"
        type="button"
        className="validation-back-btn"
        onClick={handleBack}
        aria-label="Go back"
      >
        <ChevronLeft size={16} strokeWidth={2} />
        Back
      </button>

      <div className="validation-card">
        {/* Header */}
        <div className="validation-header">
          <div className="validation-header-text">
            <h1 id="validation-title" className="validation-title">
              Enrolment Validation
            </h1>
            <p className="validation-subtitle">
              {isAccepted
                ? 'Your reference audio was checked and accepted.'
                : 'Your reference audio was checked against quality and compliance requirements.'}
            </p>
          </div>
          <div
            className={`validation-status-pill${isAccepted ? ' validation-status-pill--accepted' : ''}`}
            data-testid="validation-status-pill"
          >
            <span className="validation-pill-dot" />
            <span className="validation-pill-text">
              {isAccepted ? 'Validation Accepted' : 'Validation Rejected'}
            </span>
          </div>
        </div>

        {/* Accepted view */}
        {isAccepted && (
          <AcceptedView onGoHome={handleGoHome} />
        )}

        {/* Rejected view */}
        {!isAccepted && (
          <>
            {/* Rejection Alert Box */}
            <div
              className={`rejection-box category-${feedback.category}`}
              role="alert"
              aria-live="polite"
              data-testid="rejection-box"
            >
              <div className="rejection-icon-wrap" aria-hidden="true">
                <CategoryIcon category={feedback.category} code={feedback.canonicalCode} />
              </div>

              <div className="rejection-body">
                <div className="rejection-title-row">
                  <h2 className="rejection-title" data-testid="rejection-title">
                    {feedback.title}
                  </h2>
                  <span className="rejection-spec-badge" title="Contract reference">
                    {feedback.specReference}
                  </span>
                </div>

                <p className="rejection-message" data-testid="rejection-message">
                  {feedback.message}
                </p>

                {feedback.serverMessage && (
                  <div className="rejection-server-detail">
                    <strong>Server report:</strong> {feedback.serverMessage}
                  </div>
                )}

                <div className="rejection-meta-tags">
                  <span className="meta-tag">Code: <code>{feedback.canonicalCode}</code></span>
                  <span className="meta-tag">Category: <code>{feedback.category}</code></span>
                </div>
              </div>
            </div>

            {/* Actionable Remedy Guidance */}
            <div className="remedy-section" aria-labelledby="remedy-heading">
              <h3 id="remedy-heading" className="remedy-heading">
                <CheckCircle2 size={16} strokeWidth={2} className="remedy-heading-icon" />
                How to Resolve
              </h3>
              <p className="remedy-text" data-testid="remedy-text">
                {feedback.remedy}
              </p>

              <div className="remedy-guidelines">
                <div className="guideline-card">
                  <Clock size={16} className="guideline-icon" />
                  <div>
                    <strong>Duration</strong>
                    <span>Speak continuously for 30–60 seconds</span>
                  </div>
                </div>
                <div className="guideline-card">
                  <Mic size={16} className="guideline-icon" />
                  <div>
                    <strong>Acoustics</strong>
                    <span>Quiet room, clear voice, 15–20 cm from mic</span>
                  </div>
                </div>
                <div className="guideline-card">
                  <UserCheck size={16} className="guideline-icon" />
                  <div>
                    <strong>Identity</strong>
                    <span>Same person speaks consent, challenge &amp; reference</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Recovery Action Buttons */}
            <div className="validation-actions">
              {feedback.action === 'consent' ? (
                <button
                  id="validation-consent-btn"
                  type="button"
                  className="validation-btn validation-btn-primary"
                  onClick={handleReturnToConsent}
                  aria-label="Return to consent screen"
                >
                  <RotateCcw size={16} strokeWidth={2} />
                  Return to Consent &amp; Challenge
                </button>
              ) : (
                <button
                  id="validation-rerecord-btn"
                  type="button"
                  className="validation-btn validation-btn-primary"
                  onClick={handleRecordAgain}
                  aria-label="Record reference voice again"
                >
                  <RotateCcw size={16} strokeWidth={2} />
                  Record Again
                </button>
              )}

              <button
                id="validation-cancel-btn"
                type="button"
                className="validation-btn validation-btn-secondary"
                onClick={() => navigate('/')}
                aria-label="Return to conversation screen"
              >
                Cancel Enrolment
              </button>
            </div>

            {/* Interactive Contract Verification Switcher */}
            <div className="reason-switcher-container">
              <div className="reason-switcher-header">
                <span className="reason-switcher-title">
                  Contract Reason Inspector (Verify all supported rejection messages):
                </span>
              </div>
              <div
                className="reason-switcher-chips"
                role="radiogroup"
                aria-label="Select rejection reason code to inspect"
              >
                {Object.keys(REJECTION_FEEDBACK_DETAILS).map((code) => {
                  const item = REJECTION_FEEDBACK_DETAILS[code];
                  const isActive = selectedCode === code;
                  return (
                    <button
                      key={code}
                      type="button"
                      className={`reason-chip${isActive ? ' active' : ''}`}
                      onClick={() => setSelectedCode(code)}
                      aria-pressed={isActive}
                      title={`${item.title} (${item.specReference})`}
                    >
                      {code}
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
