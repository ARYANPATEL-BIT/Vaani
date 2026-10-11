/**
 * EnrolRecordPage — Reference voice recording UI for Vaani enrolment.
 *
 * Scope (Week 3 Day 3):
 *  - Start / Stop recording button.
 *  - Elapsed timer (mm:ss), based on actual wall-clock time.
 *  - Live level meter driven by actual AnalyserNode RMS measurements.
 *  - Duration enforcement: 30 s minimum, auto-stop at 60 s.
 *  - Re-recording: discard and start again.
 *  - All recording states exposed with clear UI feedback:
 *      idle, requesting, recording, completed, too_short, failed.
 *  - Error messages for: permission denied, no mic, recording failure,
 *    unsupported browser.
 *  - In-browser audio preview (<audio>) after a successful capture.
 *  - No backend upload; the Blob remains in memory only.
 *
 * Redirect guard: if the user lands here without passing through the
 * consent screen (/enrol), they are redirected back to /enrol.
 */

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mic, MicOff, Square, RefreshCw, CheckCircle2,
  AlertTriangle, Clock, ChevronLeft, AudioLines,
} from 'lucide-react';
import {
  useReferenceRecorder,
  MIN_DURATION_S,
  MAX_DURATION_S,
} from '../hooks/useReferenceRecorder.js';
import './EnrolRecordPage.css';

/* ── helpers ──────────────────────────────────────────────────────────── */

function formatTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
  const s = (totalSeconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

/** Width % for the progress bar (clamped 0–100). */
function progressPercent(elapsed, max) {
  return Math.min((elapsed / max) * 100, 100);
}

/* ── Level meter ──────────────────────────────────────────────────────── */

/**
 * LevelMeter — visual bar derived from real AnalyserNode RMS.
 * @param {{ level: number, active: boolean }} props
 */
function LevelMeter({ level, active }) {
  // 20 vertical bars; each lights up proportionally to the level.
  const BAR_COUNT = 20;

  return (
    <div
      className="level-meter"
      role="meter"
      aria-label="Microphone input level"
      aria-valuenow={Math.round(level * 100)}
      aria-valuemin="0"
      aria-valuemax="100"
    >
      {Array.from({ length: BAR_COUNT }, (_, i) => {
        const threshold = i / BAR_COUNT;
        const lit = active && level > threshold;
        // Colour shifts green → amber → red at the top.
        const hue = i < 13 ? 142 : i < 17 ? 45 : 0;
        return (
          <div
            key={i}
            className={`level-bar${lit ? ' lit' : ''}`}
            style={lit ? { background: `hsl(${hue}, 75%, 48%)` } : undefined}
          />
        );
      })}
    </div>
  );
}

/* ── Status badge ─────────────────────────────────────────────────────── */

const STATUS_CONFIG = {
  idle:       { label: 'Ready',      cls: 'status-idle' },
  requesting: { label: 'Requesting…', cls: 'status-requesting' },
  recording:  { label: 'Recording',  cls: 'status-recording' },
  completed:  { label: 'Complete',   cls: 'status-completed' },
  too_short:  { label: 'Too short',  cls: 'status-too-short' },
  failed:     { label: 'Error',      cls: 'status-failed' },
};

function StatusBadge({ state }) {
  const cfg = STATUS_CONFIG[state] ?? STATUS_CONFIG.idle;
  return (
    <span className={`record-status-badge ${cfg.cls}`} aria-live="polite">
      {state === 'recording' && (
        <span className="recording-dot" aria-hidden="true" />
      )}
      {cfg.label}
    </span>
  );
}

/* ── Page ─────────────────────────────────────────────────────────────── */

export default function EnrolRecordPage() {
  const navigate   = useNavigate();

  const {
    recordingState,
    elapsedSeconds,
    level,
    errorMessage,
    recordingUrl,
    startRecording,
    stopRecording,
    reRecord,
  } = useReferenceRecorder();

  const isRecording  = recordingState === 'recording';
  const isRequesting = recordingState === 'requesting';
  const isCompleted  = recordingState === 'completed';
  const isTooShort   = recordingState === 'too_short';
  const isFailed     = recordingState === 'failed';
  const isIdle       = recordingState === 'idle';

  const canStart = isIdle || isTooShort || isFailed;
  const canStop  = isRecording;
  const canReRecord = isCompleted || isTooShort || isFailed;

  const remainingSeconds = Math.max(0, MAX_DURATION_S - elapsedSeconds);
  const progress = progressPercent(elapsedSeconds, MAX_DURATION_S);

  const handleBack = useCallback(() => {
    navigate('/enrol');
  }, [navigate]);

  // Derive a colour for the progress arc:
  // 0–49% → indigo, 50–79% → amber, 80–100% → red
  const progressColor =
    progress < 50 ? 'var(--c-indigo)' :
    progress < 80 ? '#F59E0B' :
    'var(--c-red)';

  return (
    <main className="record-page" aria-labelledby="record-title">
      {/* Back link */}
      <button
        id="record-back-btn"
        type="button"
        className="record-back-btn"
        onClick={handleBack}
        aria-label="Go back to consent screen"
      >
        <ChevronLeft size={16} strokeWidth={2} />
        Back
      </button>

      <div className="record-card">
        {/* Header */}
        <div className="record-header">
          <div className="record-header-text">
            <h1 id="record-title" className="record-title">
              Reference Recording
            </h1>
            <p className="record-subtitle">
              Speak naturally for 30–60 seconds. The recording stays in your browser only.
            </p>
          </div>
          <StatusBadge state={recordingState} />
        </div>

        {/* Timer + progress */}
        <div className="record-timer-section" aria-label="Recording timer">
          <div
            className={`record-timer-display${isRecording ? ' timer-active' : ''}`}
            aria-live="off"
            aria-atomic="true"
          >
            <span className="timer-elapsed" aria-label={`Elapsed: ${formatTime(elapsedSeconds)}`}>
              {formatTime(elapsedSeconds)}
            </span>
            {isRecording && (
              <span className="timer-remaining">
                {remainingSeconds}s left
              </span>
            )}
          </div>

          {/* Progress bar */}
          <div
            className="record-progress-track"
            role="progressbar"
            aria-valuenow={elapsedSeconds}
            aria-valuemin="0"
            aria-valuemax={MAX_DURATION_S}
            aria-label="Recording progress"
          >
            <div
              className="record-progress-fill"
              style={{
                width: `${progress}%`,
                background: progressColor,
                transition: 'width 0.5s linear, background 0.3s',
              }}
            />
            {/* 30 s minimum marker */}
            <div
              className="record-progress-marker"
              style={{ left: `${(MIN_DURATION_S / MAX_DURATION_S) * 100}%` }}
              title="30-second minimum"
              aria-hidden="true"
            />
          </div>
          <div className="record-progress-labels" aria-hidden="true">
            <span>0:00</span>
            <span className="record-min-label">0:30 min</span>
            <span>1:00</span>
          </div>
        </div>

        {/* Level meter */}
        <div className="record-level-section">
          <div className="level-label-row">
            <AudioLines size={14} strokeWidth={1.8} aria-hidden="true" />
            <span className="level-label-text">
              {isRecording ? 'Live microphone level' : 'Microphone level'}
            </span>
          </div>
          <LevelMeter level={level} active={isRecording} />
        </div>

        {/* Mic visual / state indicator */}
        <div className="record-mic-visual-wrap">
          <div
            className={`record-mic-visual${isRecording ? ' mic-recording' : ''}${isRequesting ? ' mic-requesting' : ''}`}
            aria-hidden="true"
          >
            {isFailed ? (
              <MicOff size={32} strokeWidth={1.6} />
            ) : isCompleted ? (
              <CheckCircle2 size={32} strokeWidth={1.6} />
            ) : (
              <Mic size={32} strokeWidth={1.6} />
            )}
          </div>
        </div>

        {/* State-specific messages */}
        {isTooShort && (
          <div className="record-feedback record-feedback-warning" role="alert">
            <AlertTriangle size={16} strokeWidth={2} aria-hidden="true" />
            <div>
              <strong>Recording too short.</strong>
              {' '}You recorded {elapsedSeconds}s but the minimum is {MIN_DURATION_S}s.
              Please record again and speak for at least 30 seconds.
            </div>
          </div>
        )}

        {isFailed && errorMessage && (
          <div className="record-feedback record-feedback-error" role="alert">
            <AlertTriangle size={16} strokeWidth={2} aria-hidden="true" />
            <div>
              <strong>Could not record.</strong>
              {' '}{errorMessage}
            </div>
          </div>
        )}

        {isCompleted && (
          <div className="record-feedback record-feedback-success" role="status">
            <CheckCircle2 size={16} strokeWidth={2} aria-hidden="true" />
            <div>
              <strong>Recording saved ({elapsedSeconds}s).</strong>
              {' '}Your reference voice is ready. You can preview it below or record again.
            </div>
          </div>
        )}

        {/* Audio preview (completed only) */}
        {isCompleted && recordingUrl && (
          <div className="record-preview-section">
            <p className="record-preview-label">Preview your recording:</p>
            <audio
              id="record-preview-audio"
              className="record-preview-audio"
              src={recordingUrl}
              controls
              aria-label="Preview of your reference voice recording"
            />
          </div>
        )}

        {/* Guidance (visible when idle or in early recording) */}
        {(isIdle || isRequesting) && (
          <ul className="record-guidance-list" role="list" aria-label="Recording tips">
            <li><Clock size={13} aria-hidden="true" /> Speak for at least 30 seconds</li>
            <li><Mic  size={13} aria-hidden="true" /> Use your normal speaking voice</li>
            <li><AudioLines size={13} aria-hidden="true" /> Find a quiet room with minimal echo</li>
          </ul>
        )}

        {/* Control buttons */}
        <div className="record-controls">
          {canStart && (
            <button
              id="record-start-btn"
              type="button"
              className="record-btn record-btn-start"
              onClick={startRecording}
              disabled={isRequesting}
              aria-label="Start recording"
            >
              <Mic size={18} strokeWidth={1.8} />
              {isRequesting ? 'Requesting microphone…' : 'Start Recording'}
            </button>
          )}

          {canStop && (
            <button
              id="record-stop-btn"
              type="button"
              className="record-btn record-btn-stop"
              onClick={stopRecording}
              aria-label="Stop recording"
            >
              <Square size={18} strokeWidth={1.8} />
              Stop Recording
            </button>
          )}

          {canReRecord && (
            <button
              id="record-rerecord-btn"
              type="button"
              className="record-btn record-btn-rerecord"
              onClick={reRecord}
              aria-label="Discard and record again"
            >
              <RefreshCw size={16} strokeWidth={2} />
              Record Again
            </button>
          )}
        </div>

        {/* Bottom note */}
        <p className="record-bottom-note">
          Your recording is stored in browser memory only and is not sent to any server during this step.
        </p>
      </div>
    </main>
  );
}
