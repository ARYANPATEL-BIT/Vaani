/**
 * ConversationPage — main voice conversation interface.
 *
 * Week 1, Day 2: microphone capture → WebSocket streaming (16 kHz Int16LE PCM).
 * Week 1, Day 3: incoming server audio → playback queue → gapless speaker output.
 * Week 1, Day 4: audio.flush / flush.ack for immediate playback silencing.
 * Week 2, Day 1: explicit Connect / Disconnect actions, session status badge,
 *   persona selector. The session state machine is driven by wsStatus values
 *   from useAudioCapture, which directly reflect the WebSocket / protocol events
 *   defined in docs/contracts.md §2.3 and backend/vaani/protocol.py.
 *
 * Persona note: the backend protocol.py SessionStart model accepts any string
 * for `persona`; only "default" is currently meaningful in the backend.
 * The selector lists only the value the backend will act on without error.
 * Additional personas will be added here as the backend implements them.
 */

import { useState, useEffect, useCallback } from 'react';
import { useAudioCapture } from '../hooks/useAudioCapture.js';
import { usePlaybackQueue } from '../hooks/usePlaybackQueue.js';
import { useTranscript } from '../hooks/useTranscript.js';
import { useLatencyTelemetry } from '../hooks/useLatencyTelemetry.js';
import { TranscriptView } from '../components/TranscriptView.jsx';
import { LatencyHud } from '../components/LatencyHud.jsx';
import './ConversationPage.css';

/**
 * Valid persona values known to the backend at this protocol revision.
 * Source: backend/vaani/protocol.py SessionStart (persona: str = "default").
 * Only "default" is meaningful; additional values are listed as a
 * forward-declaration for the UI, not claimed to be implemented by the backend.
 */
const PERSONA_OPTIONS = [
  { value: 'default', label: 'Default' },
];

export default function ConversationPage() {
  // --- Persona selector state (Week 2, Day 1) ---
  // selectedPersona is held here because it must survive connect/disconnect
  // cycles: the user should be able to pick a persona before connecting and
  // keep their choice after disconnecting.
  const [selectedPersona, setSelectedPersona] = useState('default');

  // Playback queue: enqueue() accepts an ArrayBuffer and plays it gaplessly.
  const { enqueue, flushPlayback } = usePlaybackQueue();

  // Transcript state: manages live active partial and immutable finalized speech turns
  const {
    finalTranscriptEntries,
    currentPartialTranscript,
    updatePartial,
    finalizeTurn,
    clearActivePartial,
    resetTranscript,
  } = useTranscript();

  // Latency telemetry state: manages live per-stage timings from server messages (Week 3, Day 1)
  const {
    telemetryData,
    processServerMessage: processTelemetryMessage,
    resetTelemetry,
  } = useLatencyTelemetry();

  const {
    isCapturing,
    micStatus,
    wsStatus,
    sessionId,
    framesSent,
    fps,
    errorMessage,
    startCapture,
    stopCapture,
  } = useAudioCapture();

  // ---- Session state helpers -----------------------------------------------
  //
  // wsStatus values and their meanings (from useAudioCapture / contracts.md):
  //   'disconnected' — no WebSocket, no session.
  //   'connecting'   — WebSocket TCP handshake in progress.
  //   'connected'    — WebSocket open; session.start sent; awaiting session.started.
  //   'ready'        — session.started received; session fully active.
  //   'error'        — WebSocket or protocol error.

  const isTransitioning = wsStatus === 'connecting' || wsStatus === 'connected';
  const hasError = wsStatus === 'error';

  /**
   * Map wsStatus to a human-readable label and CSS class for the status badge.
   * Only statuses that useAudioCapture actually sets are handled here.
   */
  const getSessionStatusDisplay = () => {
    switch (wsStatus) {
      case 'connecting':
        return { label: 'Connecting…', className: 'status-warning' };
      case 'connected':
        return { label: 'Starting session…', className: 'status-warning' };
      case 'ready':
        return { label: 'Session active', className: 'status-active' };
      case 'error':
        return { label: 'Connection error', className: 'status-error' };
      default:
        return { label: 'Disconnected', className: 'status-idle' };
    }
  };

  const getMicStatusDisplay = () => {
    switch (micStatus) {
      case 'requesting':
        return { label: 'Requesting permission…', className: 'status-warning' };
      case 'active':
        return { label: 'Capturing (16 kHz mono)', className: 'status-active' };
      case 'denied':
        return { label: 'Permission denied', className: 'status-error' };
      case 'error':
        return { label: 'Error', className: 'status-error' };
      default:
        return { label: 'Idle', className: 'status-idle' };
    }
  };

  const session = getSessionStatusDisplay();
  const mic = getMicStatusDisplay();

  // ---- Handlers ------------------------------------------------------------

  /**
   * Route incoming JSON control messages from the WebSocket.
   * Dispatches speech transcripts to useTranscript, and telemetry frames
   * to useLatencyTelemetry.
   */
  const handleServerMessage = useCallback((msg) => {
    if (!msg || typeof msg !== 'object') return;

    if (msg.type === 'transcript.partial') {
      updatePartial(msg.text);
    } else if (msg.type === 'transcript.final') {
      finalizeTurn(msg.text);
    }

    processTelemetryMessage(msg);
  }, [updatePartial, finalizeTurn, processTelemetryMessage]);

  /**
   * Connect: start audio capture and open the WebSocket session.
   * Resets transcript and telemetry so stale turns from a previous session do not carry over.
   * The persona chosen in the selector is passed to useAudioCapture which
   * includes it in the session.start control message per contracts.md §2.3.
   * Guard: if already capturing, this is a no-op (useAudioCapture also guards).
   */
  const handleConnect = () => {
    if (isCapturing) return;
    resetTranscript();
    resetTelemetry();
    startCapture(enqueue, flushPlayback, selectedPersona, handleServerMessage);
  };

  /**
   * Disconnect: send session.end, close WebSocket, release audio resources.
   * Clears any active in-flight partial transcript so it does not linger.
   * Finalized transcript entries remain visible until a new session starts.
   * stopCapture() performs all cleanup per useAudioCapture's teardown sequence.
   */
  const handleDisconnect = () => {
    clearActivePartial();
    stopCapture();
  };

  // Clear in-flight active partial whenever the session ends or errors
  useEffect(() => {
    if (wsStatus === 'disconnected' || wsStatus === 'error') {
      clearActivePartial();
    }
  }, [wsStatus, clearActivePartial]);

  /**
   * Persona change: only allowed when disconnected to avoid mid-session
   * persona switching (the backend associates a persona with a session at
   * session.start time; it cannot be changed while the session is live).
   */
  const handlePersonaChange = (e) => {
    if (!isCapturing) {
      setSelectedPersona(e.target.value);
    }
  };

  return (
    <main className="conversation-page">
      <div className="header-section">
        <h1>Vaani</h1>
        <p className="subtitle">Real-time voice conversation</p>
      </div>

      {/* Error banner — shown for connection / protocol errors */}
      {errorMessage && (
        <div className="error-banner" role="alert">
          <span className="error-icon">⚠️</span>
          <span>{errorMessage}</span>
        </div>
      )}

      {/* ---- Session status badge (Week 2, Day 1) ---- */}
      <div className="session-status-row" aria-label="Session status">
        <span className={`session-status-badge ${session.className}`}>
          <span className="status-dot" />
          {session.label}
        </span>
        {sessionId && (
          <span className="session-id-display" title="Session ID">
            ID: {sessionId.slice(0, 8)}…
          </span>
        )}
      </div>

      {/* ---- Persona selector (Week 2, Day 1) ---- */}
      {/*
        The selector is always visible so the user can see and choose their
        persona before connecting. It is disabled while a session is active
        because the backend binds the persona at session.start time.
      */}
      <div className="persona-section">
        <label htmlFor="persona-select" className="persona-label">
          Persona
        </label>
        <select
          id="persona-select"
          className="persona-select"
          value={selectedPersona}
          onChange={handlePersonaChange}
          disabled={isCapturing}
          aria-describedby="persona-hint"
        >
          {PERSONA_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <p id="persona-hint" className="persona-hint">
          {isCapturing
            ? 'Persona cannot be changed while a session is active.'
            : 'Choose a persona before connecting.'}
        </p>
      </div>

      {/* ---- Connect / Disconnect controls (Week 2, Day 1) ---- */}
      <div className="controls-section">
        {!isCapturing ? (
          <button
            type="button"
            className="action-btn start-btn"
            onClick={handleConnect}
            id="connect-btn"
            disabled={isTransitioning}
            aria-label="Connect and start voice session"
          >
            Connect
          </button>
        ) : (
          <button
            type="button"
            className="action-btn stop-btn"
            onClick={handleDisconnect}
            id="disconnect-btn"
            aria-label="Disconnect and end voice session"
          >
            {hasError ? 'Close' : 'Disconnect'}
          </button>
        )}
      </div>

      {/* ---- Live Transcript section (Week 2, Day 2) ---- */}
      <TranscriptView
        finalTranscriptEntries={finalTranscriptEntries}
        currentPartialTranscript={currentPartialTranscript}
        isCapturing={isCapturing}
      />

      {/* ---- Latency HUD (Week 3, Day 1) ---- */}
      <LatencyHud
        telemetryData={telemetryData}
        wsStatus={wsStatus}
        isCapturing={isCapturing}
      />

      {/* ---- Diagnostics panel (Week 1 preserved) ---- */}
      <section className="status-panel" aria-label="Audio pipeline status">
        <h2 className="status-panel-title">Audio Pipeline Diagnostics</h2>

        <div className="status-row">
          <span className="status-label">Session</span>
          <span className={`status-value ${session.className}`}>
            <span className="status-dot" />
            {session.label}
          </span>
        </div>

        <div className="status-row">
          <span className="status-label">Microphone</span>
          <span className={`status-value ${mic.className}`}>
            <span className="status-dot" />
            {mic.label}
          </span>
        </div>

        <div className="status-row">
          <span className="status-label">Persona</span>
          <span className="status-value metrics-value">
            {isCapturing ? selectedPersona : '—'}
          </span>
        </div>

        <div className="status-row">
          <span className="status-label">Audio Format</span>
          <span className="status-value">16 kHz / 20 ms / 640 B Int16</span>
        </div>

        <div className="status-row">
          <span className="status-label">Frames Sent</span>
          <span className="status-value metrics-value">{framesSent.toLocaleString()}</span>
        </div>

        <div className="status-row">
          <span className="status-label">Frame Rate</span>
          <span className="status-value metrics-value">
            {fps} fps <span className="target-fps">(target ~50)</span>
          </span>
        </div>

        <div className="status-row">
          <span className="status-label">Playback</span>
          <span className={`status-value ${wsStatus === 'ready' ? 'status-active' : 'status-idle'}`}>
            <span className="status-dot" />
            {wsStatus === 'ready' ? 'Playback ready' : 'Waiting for session'}
          </span>
        </div>
      </section>

      <p className="hint">
        Audio is processed on a dedicated AudioWorklet thread and streamed as 20 ms binary frames.
        Incoming server audio is scheduled gaplessly via the Web Audio clock.
      </p>
    </main>
  );
}
