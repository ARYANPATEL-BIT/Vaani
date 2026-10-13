/**
 * ConversationPage — Voice conversation screen for Vaani.
 *
 * Implements Week 3 Day 2 functionality:
 * - Turn states in the UI (idle, listening, thinking, speaking, cancelling/interrupted)
 * - Agent reply streaming progressively as text
 * - Interrupted turns clearly marked (preserving streamed text + visual indicator)
 * - Error states with clear messages and recovery actions:
 *     1. Microphone denied
 *     2. Connection dropped
 *     3. Provider failure
 * - Preserves existing visual direction (warm cream canvas, central VoiceOrb,
 *   real personas, collapsible latency HUD, bottom controls).
 * - Push-to-talk (docs/contracts.md §2.8): a mode choice before connect, sent
 *   as session.start's mode, and a Speak/Stop control (PttButton) in a
 *   session the server confirmed as "ptt".
 */

import { useState, useEffect, useCallback } from 'react';
import { useAudioCapture } from '../hooks/useAudioCapture.js';
import { usePlaybackQueue } from '../hooks/usePlaybackQueue.js';
import { useTranscript } from '../hooks/useTranscript.js';
import { useTurnState } from '../hooks/useTurnState.js';
import { useLatencyTelemetry } from '../hooks/useLatencyTelemetry.js';
import { VoiceOrb } from '../components/VoiceOrb/VoiceOrb.jsx';
import { TranscriptView } from '../components/TranscriptView.jsx';
import { LatencyHud } from '../components/LatencyHud.jsx';
import { PttButton } from '../components/PttButton.jsx';
import './ConversationPage.css';

/**
 * Real personas implemented in backend/config.toml [personas].
 */
const PERSONAS = [
  { id: 'default', label: 'Default', desc: 'Friendly voice assistant' },
  { id: 'tutor', label: 'Tutor', desc: 'Patient explanations & checks' },
  { id: 'support', label: 'Support', desc: 'Concise & practical help' },
];

/**
 * Input modes of session.start (protocol v0.9, docs/contracts.md §2.8).
 */
const MODES = [
  { id: 'vad', label: 'Hands-free', desc: 'Just talk; a pause ends your turn' },
  { id: 'ptt', label: 'Push-to-talk', desc: 'Press Speak to talk, Stop when done' },
];

export default function ConversationPage() {
  const [selectedPersona, setSelectedPersona] = useState('default');
  const [selectedMode, setSelectedMode] = useState('vad');
  const [showTelemetry, setShowTelemetry] = useState(false);

  // Playback queue: gapless PCM scheduling + dynamic sample rate handling
  const { enqueue, flushPlayback, setPlaybackSampleRate } = usePlaybackQueue();

  // Backend turn state mirror (idle, listening, thinking, speaking, cancelling)
  const {
    turnState,
    processTurnMessage,
    resetTurnState,
  } = useTurnState();

  // Transcript state: manages user turns, streaming agent replies, and interrupted turns
  const {
    finalTranscriptEntries,
    currentPartialTranscript,
    currentAgentPartial,
    updatePartial,
    finalizeTurn,
    appendAgentDelta,
    finalizeAgentTurn,
    interruptAgentTurn,
    clearActivePartial,
    resetTranscript,
  } = useTranscript();

  // Real pipeline latency telemetry
  const {
    telemetryData,
    processServerMessage: processTelemetryMessage,
    resetTelemetry,
  } = useLatencyTelemetry();

  // Audio capture pipeline & WebSocket session lifecycle
  const {
    isCapturing,
    micStatus,
    wsStatus,
    sessionId,
    errorMessage,
    clearError,
    startCapture,
    stopCapture,
    sessionMode,
    pressState,
    pttStart,
    pttStop,
  } = useAudioCapture();

  const isTransitioning = wsStatus === 'connecting' || wsStatus === 'connected';
  const isConnected = wsStatus === 'ready';

  /**
   * Central server message router.
   * Dispatches protocol events to audio, transcript, turn state, and telemetry.
   */
  const handleServerMessage = useCallback((msg) => {
    if (!msg || typeof msg !== 'object') return;

    // Dynamic sample rate for Piper TTS (declared in audio.start)
    if (msg.type === 'audio.start' && msg.sample_rate) {
      setPlaybackSampleRate(msg.sample_rate);
    }

    // User speech transcripts
    if (msg.type === 'transcript.partial') {
      updatePartial(msg.text);
    } else if (msg.type === 'transcript.final') {
      finalizeTurn(msg.text);
    }

    // Backend turn state transitions
    if (msg.type === 'turn.state') {
      processTurnMessage(msg);
      if (msg.state === 'cancelling') {
        interruptAgentTurn('Interrupted', msg.turn_id);
      }
    }

    // Streaming agent replies. The turn_id is kept on the entry, so a later
    // audio.flush for that turn can still mark it interrupted.
    if (msg.type === 'agent.text') {
      processTurnMessage(msg);
      appendAgentDelta(msg.delta, msg.turn_id);
    } else if (msg.type === 'agent.done') {
      processTurnMessage(msg);
      finalizeAgentTurn(msg.text, msg.turn_id);
    }

    // Audio flush command (cancellation). Also marks a reply that was
    // already complete (agent.done) but still playing.
    if (msg.type === 'audio.flush') {
      interruptAgentTurn('Interrupted', msg.turn_id);
    }

    // Server error report (provider failure, safety guardrail, recognizer, etc.)
    // The reply text already streamed is KEPT as a transcript line: after
    // TTS_FAILED (or LLM_FAILED mid-reply) no agent.done follows to keep it,
    // and the banner says what went wrong. Only the user's partial is cleared.
    if (msg.type === 'error') {
      finalizeAgentTurn();
      updatePartial(null);
    }

    // Pipeline telemetry
    processTelemetryMessage(msg);
  }, [
    setPlaybackSampleRate,
    updatePartial,
    finalizeTurn,
    processTurnMessage,
    appendAgentDelta,
    finalizeAgentTurn,
    interruptAgentTurn,
    processTelemetryMessage,
  ]);

  /**
   * Connect: start microphone capture and WebSocket session.
   */
  const handleConnect = useCallback(() => {
    if (isCapturing) return;
    resetTranscript();
    resetTelemetry();
    resetTurnState();
    startCapture(enqueue, flushPlayback, selectedPersona, handleServerMessage, selectedMode);
  }, [
    isCapturing,
    resetTranscript,
    resetTelemetry,
    resetTurnState,
    startCapture,
    enqueue,
    flushPlayback,
    selectedPersona,
    handleServerMessage,
    selectedMode,
  ]);

  /**
   * Speak pressed (button or Space). If it cut the agent off, the hook has
   * already stopped playback; here the cut reply is marked interrupted at
   * once, without waiting for the server's audio.flush.
   */
  const handleSpeak = useCallback(() => {
    const cutTurnId = pttStart();
    if (cutTurnId) {
      interruptAgentTurn('Interrupted', cutTurnId);
    }
  }, [pttStart, interruptAgentTurn]);

  /**
   * Disconnect: cleanly end session and release microphone.
   */
  const handleDisconnect = useCallback(() => {
    clearActivePartial();
    resetTurnState();
    stopCapture();
  }, [clearActivePartial, resetTurnState, stopCapture]);

  // Reset active partials when disconnected or error occurs
  useEffect(() => {
    if (wsStatus === 'disconnected' || wsStatus === 'error') {
      clearActivePartial();
      resetTurnState();
    }
  }, [wsStatus, clearActivePartial, resetTurnState]);

  const isMicDenied = micStatus === 'denied';
  const isConnectionDropped = Boolean(
    errorMessage && errorMessage.toLowerCase().includes('connection')
  );

  return (
    <div className="conversation-container">
      {/* Top Bar: Title & Session Info */}
      <header className="conversation-header">
        <div className="header-brand">
          <h1 className="header-title">Vaani</h1>
          <span className="header-subtitle">Real-time Hindi & English voice assistant</span>
        </div>

        <div className="header-actions">
          {/* Persona selector (disabled while session is active) */}
          <div className="persona-picker" title={isCapturing ? 'Persona is fixed for active session' : 'Choose persona'}>
            <span className="persona-picker-label">Persona:</span>
            <div className="persona-options">
              {PERSONAS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`persona-chip ${selectedPersona === p.id ? 'active' : ''}`}
                  onClick={() => !isCapturing && setSelectedPersona(p.id)}
                  disabled={isCapturing}
                  title={p.desc}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Input mode selector (fixed for the session, like the persona) */}
          <div className="persona-picker" title={isCapturing ? 'Mode is fixed for active session' : 'Choose input mode'}>
            <span className="persona-picker-label">Mode:</span>
            <div className="persona-options">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className={`persona-chip ${selectedMode === m.id ? 'active' : ''}`}
                  onClick={() => !isCapturing && setSelectedMode(m.id)}
                  disabled={isCapturing}
                  title={m.desc}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Turn State Pill: the server's latest turn.state, shown verbatim */}
          {isConnected && (
            <div className={`session-pill turn-pill turn-${turnState}`} data-testid="turn-state-pill">
              <span className="status-indicator" />
              <span className="status-text">{turnState}</span>
            </div>
          )}

          {/* Session Status Pill */}
          <div className={`session-pill status-${wsStatus}`}>
            <span className="status-indicator" />
            <span className="status-text">
              {wsStatus === 'ready'
                ? 'Connected'
                : wsStatus === 'connecting' || wsStatus === 'connected'
                ? 'Connecting…'
                : wsStatus === 'error'
                ? 'Error'
                : 'Disconnected'}
            </span>
            {sessionId && (
              <span className="session-id-tag" title={sessionId}>
                {sessionId.slice(0, 6)}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Comprehensive Failure & Error Notification Screens */}
      {errorMessage && (
        <div
          className={`error-banner ${
            isMicDenied
              ? 'error-mic-denied'
              : isConnectionDropped
              ? 'error-connection-dropped'
              : 'error-provider'
          }`}
          role="alert"
        >
          <div className="error-icon-wrap" aria-hidden="true">
            <svg className="error-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
          </div>
          <div className="error-content">
            <div className="error-title-row">
              <strong className="error-title">
                {isMicDenied
                  ? 'Microphone Permission Denied'
                  : isConnectionDropped
                  ? 'Connection Dropped'
                  : 'Service Error'}
              </strong>
            </div>
            <p className="error-text">{errorMessage}</p>
          </div>
          <div className="error-actions">
            {isMicDenied && (
              <button
                type="button"
                className="error-action-btn"
                onClick={handleConnect}
              >
                Try Again
              </button>
            )}
            {isConnectionDropped && !isCapturing && (
              <button
                type="button"
                className="error-action-btn"
                onClick={handleConnect}
              >
                Reconnect
              </button>
            )}
            <button
              type="button"
              className="error-dismiss-btn"
              onClick={clearError}
              aria-label="Dismiss error notification"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main Conversation Experience */}
      <div className="conversation-stage">
        {/* Central Voice Orb Presence */}
        <section className="orb-section">
          <VoiceOrb
            turnState={turnState}
            isConnected={isConnected}
            isTransitioning={isTransitioning}
            // Only mic and connection failures take over the orb. A per-turn
            // server error (LLM_FAILED etc.) shows in the banner while the orb
            // keeps showing the live turn state.
            errorMessage={isMicDenied || isConnectionDropped || wsStatus === 'error' ? errorMessage : null}
            onClick={!isConnected ? handleConnect : undefined}
            mode={sessionMode}
          />
        </section>

        {/* Real Conversation Transcript Stream */}
        <section className="transcript-wrapper">
          <TranscriptView
            finalTranscriptEntries={finalTranscriptEntries}
            currentPartialTranscript={currentPartialTranscript}
            currentAgentPartial={currentAgentPartial}
            isCapturing={isCapturing}
            turnState={turnState}
          />
        </section>

        {/* Collapsible Pipeline Telemetry */}
        <section className="telemetry-collapsible">
          <button
            type="button"
            className="telemetry-toggle-btn"
            onClick={() => setShowTelemetry((prev) => !prev)}
            aria-expanded={showTelemetry}
          >
            <span className="telemetry-toggle-icon">⚡</span>
            <span>{showTelemetry ? 'Hide Pipeline Latency' : 'View Pipeline Latency Telemetry'}</span>
            {telemetryData?.totalMs && (
              <span className="telemetry-total-pill">{Math.round(telemetryData.totalMs)} ms</span>
            )}
          </button>

          {showTelemetry && (
            <div className="telemetry-drawer">
              <LatencyHud
                telemetryData={telemetryData}
                wsStatus={wsStatus}
                isCapturing={isCapturing}
              />
            </div>
          )}
        </section>
      </div>

      {/* Floating Bottom Control Bar */}
      <div className="bottom-bar-container">
        <div className="floating-controls-bar">
          {!isCapturing ? (
            <button
              type="button"
              id="connect-btn"
              className="control-btn primary-connect-btn"
              onClick={handleConnect}
              disabled={isTransitioning}
              aria-label="Connect and start voice session"
            >
              <div className="btn-icon-wrapper">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15a3 3 0 01-3-3V4.5a3 3 0 116 0v7.5a3 3 0 01-3 3z" />
                </svg>
              </div>
              <span className="btn-label">
                {isTransitioning ? 'Connecting…' : 'Start Conversation'}
              </span>
            </button>
          ) : (
            <>
              {isConnected && sessionMode === 'ptt' && (
                <PttButton pressState={pressState} onSpeak={handleSpeak} onStop={pttStop} />
              )}
              <button
                type="button"
                id="disconnect-btn"
                className="control-btn disconnect-btn"
                onClick={handleDisconnect}
                aria-label="End conversation session"
              >
                <div className="btn-icon-wrapper disconnect-icon-wrapper">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </div>
                <span className="btn-label">End Conversation</span>
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
