/**
 * LoopbackPage — Week 2 Day 5 loopback measurement rig UI.
 *
 * Accessible at /loopback. Completely isolated from the conversation pipeline:
 * it creates its own AudioContext, requests its own microphone permission,
 * and disposes everything on unmount.
 *
 * What the user sees:
 *   1. A "Run Measurement" button.
 *   2. Status updates as the rig progresses.
 *   3. A results panel showing the waveform-derived round-trip delay.
 *   4. Clear errors if the signal is not detected.
 */

import { useLoopbackMeasurement } from '../loopback/useLoopbackMeasurement.js';
import {
  REFERENCE_FREQ_HZ,
  REFERENCE_DURATION_S,
  RECORD_DURATION_S,
  MIN_PEAK_QUALITY,
} from '../loopback/loopbackAnalysis.js';
import './LoopbackPage.css';

/**
 * Human-readable status labels for each rig state.
 */
const STATUS_LABELS = {
  idle: { text: 'Ready', className: 'status-idle' },
  requesting: { text: 'Requesting microphone permission…', className: 'status-warning' },
  recording: {
    text: `Recording (${RECORD_DURATION_S.toFixed(1)} s window)…`,
    className: 'status-warning',
  },
  analysing: { text: 'Analysing waveforms…', className: 'status-warning' },
  done: { text: 'Measurement complete', className: 'status-active' },
  error: { text: 'Measurement failed', className: 'status-error' },
};

export default function LoopbackPage() {
  const { status, result, errorMessage, measure, reset } =
    useLoopbackMeasurement();

  const statusInfo = STATUS_LABELS[status] ?? STATUS_LABELS.idle;
  const isBusy =
    status === 'requesting' || status === 'recording' || status === 'analysing';

  return (
    <main className="loopback-page">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="loopback-header">
        <h1>Loopback Measurement Rig</h1>
        <p className="loopback-subtitle">
          Week 2 · Day 5 — measures real speaker→microphone round-trip delay
          from waveform cross-correlation.
        </p>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* How-it-works info box                                               */}
      {/* ------------------------------------------------------------------ */}
      <section className="info-box" aria-label="Measurement method">
        <h2 className="info-box-title">How it works</h2>
        <ol className="info-steps">
          <li>
            Plays a {REFERENCE_FREQ_HZ} Hz sine tone ({REFERENCE_DURATION_S} s)
            through your speaker.
          </li>
          <li>Records your microphone for {RECORD_DURATION_S.toFixed(1)} s simultaneously.</li>
          <li>
            Runs cross-correlation to find where the tone appears in the
            recording.
          </li>
          <li>
            Reports{' '}
            <code>offset_samples ÷ sample_rate × 1000 = delay_ms</code>.
          </li>
        </ol>
        <p className="info-note">
          <strong>Physical setup required.</strong> The speaker output must
          reach the microphone — either acoustically (speaker near mic) or via
          a loopback cable. Echo cancellation is disabled during measurement so
          the reference tone is captured.
        </p>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* Status badge                                                        */}
      {/* ------------------------------------------------------------------ */}
      <div className="loopback-status-row" aria-live="polite">
        <span className={`loopback-status-badge ${statusInfo.className}`}>
          <span className="status-dot" />
          {statusInfo.text}
        </span>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Error banner                                                        */}
      {/* ------------------------------------------------------------------ */}
      {errorMessage && (
        <div className="loopback-error" role="alert">
          <span className="error-icon">⚠️</span>
          <span>{errorMessage}</span>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Controls                                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="loopback-controls">
        {status !== 'done' && status !== 'error' ? (
          <button
            id="loopback-run-btn"
            type="button"
            className="loopback-btn primary-btn"
            onClick={measure}
            disabled={isBusy}
            aria-label="Run loopback measurement"
          >
            {isBusy ? 'Measuring…' : 'Run Measurement'}
          </button>
        ) : (
          <button
            id="loopback-reset-btn"
            type="button"
            className="loopback-btn secondary-btn"
            onClick={reset}
            aria-label="Reset and measure again"
          >
            Measure Again
          </button>
        )}
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Results panel (only shown when done)                                */}
      {/* ------------------------------------------------------------------ */}
      {status === 'done' && result && (
        <section className="results-panel" aria-label="Measurement results">
          <h2 className="results-title">Results</h2>

          <div className="results-grid">
            <span className="res-label">Input device</span>
            <span className="res-value">{result.inputLabel}</span>

            <span className="res-label">Sample rate</span>
            <span className="res-value">{result.sampleRate.toLocaleString()} Hz</span>

            <span className="res-label">Reference signal</span>
            <span className="res-value">
              {REFERENCE_FREQ_HZ} Hz sine · {REFERENCE_DURATION_S} s
            </span>

            <span className="res-label">Reference detected</span>
            <span
              className={`res-value ${
                result.peakQuality >= MIN_PEAK_QUALITY ? 'value-good' : 'value-warn'
              }`}
            >
              {result.peakQuality >= MIN_PEAK_QUALITY ? 'YES ✓' : 'WEAK ⚠'}
            </span>

            <span className="res-label">Waveform offset</span>
            <span className="res-value">
              {result.offsetSamples.toLocaleString()} samples
            </span>

            <span className="res-label">Correlation quality</span>
            <span
              className={`res-value ${
                result.peakQuality >= MIN_PEAK_QUALITY ? 'value-good' : 'value-warn'
              }`}
            >
              {(result.peakQuality * 100).toFixed(1)}%
              {' '}(threshold {(MIN_PEAK_QUALITY * 100).toFixed(0)}%)
            </span>
          </div>

          {/* Headline delay number */}
          <div
            className={`delay-headline ${
              result.peakQuality >= MIN_PEAK_QUALITY
                ? 'delay-good'
                : 'delay-warn'
            }`}
            aria-label={`Round-trip delay: ${result.delayMs} milliseconds`}
          >
            <span className="delay-label">Round-trip delay</span>
            <span className="delay-value">{result.delayMs.toFixed(2)} ms</span>
            <span className="delay-formula">
              = {result.offsetSamples} samples ÷ {result.sampleRate} Hz × 1000
            </span>
          </div>

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <div className="results-warnings" role="alert">
              <p className="warnings-title">⚠ Measurement warnings</p>
              <ul className="warnings-list">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {result.peakQuality < MIN_PEAK_QUALITY && (
            <p className="low-quality-hint">
              The reference signal was not reliably detected. Ensure your
              speaker output is physically reaching the microphone (place the
              speaker near the mic or use a loopback cable), and retry.
            </p>
          )}
        </section>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Setup instructions                                                  */}
      {/* ------------------------------------------------------------------ */}
      <section className="setup-section" aria-label="Hardware setup">
        <h2 className="setup-title">Hardware setup</h2>
        <div className="setup-options">
          <div className="setup-option">
            <span className="setup-icon">🔊→🎤</span>
            <div>
              <strong>Acoustic coupling</strong>
              <p>
                Play at moderate volume with a microphone 5–30 cm from the
                speaker in a quiet room. No cable required.
              </p>
            </div>
          </div>
          <div className="setup-option">
            <span className="setup-icon">🔌</span>
            <div>
              <strong>Loopback cable</strong>
              <p>
                Connect a 3.5 mm TRS cable from the headphone jack to the
                microphone jack. Gives the cleanest signal on laptops that
                expose both ports.
              </p>
            </div>
          </div>
        </div>
        <p className="setup-note">
          The rig disables echo cancellation and noise suppression during
          measurement so the reference tone is preserved in the recording.
          Normal Vaani voice sessions are unaffected.
        </p>
      </section>
    </main>
  );
}
