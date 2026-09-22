/**
 * ConversationPage — main voice conversation interface.
 *
 * Implements Week 1, Day 2 microphone capture:
 * - Prompts user for microphone access on explicit click.
 * - Captures 16 kHz mono audio using AudioWorklet (audio-processor.js).
 * - Packages audio into 20 ms Int16 PCM frames (320 samples / 640 bytes).
 * - Streams binary frames over WebSocket to Aryan's gateway.
 * - Telemetry panel displaying frame count, live frame rate (~50 fps), and connection status.
 */

import { useAudioCapture } from '../hooks/useAudioCapture.js';
import './ConversationPage.css';

export default function ConversationPage() {
  const {
    isCapturing,
    micStatus,
    wsStatus,
    framesSent,
    fps,
    errorMessage,
    startCapture,
    stopCapture,
  } = useAudioCapture();

  const getMicStatusDisplay = () => {
    switch (micStatus) {
      case 'requesting':
        return { label: 'Requesting permission...', className: 'status-warning' };
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

  const getWsStatusDisplay = () => {
    switch (wsStatus) {
      case 'connecting':
        return { label: 'Connecting...', className: 'status-warning' };
      case 'connected':
        return { label: 'Connected (starting session)', className: 'status-warning' };
      case 'ready':
        return { label: 'Session ready (streaming)', className: 'status-active' };
      case 'error':
        return { label: 'Connection error', className: 'status-error' };
      default:
        return { label: 'Disconnected', className: 'status-idle' };
    }
  };

  const mic = getMicStatusDisplay();
  const ws = getWsStatusDisplay();

  return (
    <main className="conversation-page">
      <div className="header-section">
        <h1>Vaani</h1>
        <p className="subtitle">Real-time voice conversation</p>
      </div>

      {errorMessage && (
        <div className="error-banner" role="alert">
          <span className="error-icon">⚠️</span>
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="controls-section">
        {!isCapturing ? (
          <button
            type="button"
            className="action-btn start-btn"
            onClick={startCapture}
            id="start-mic-btn"
          >
            Start Microphone
          </button>
        ) : (
          <button
            type="button"
            className="action-btn stop-btn"
            onClick={stopCapture}
            id="stop-mic-btn"
          >
            Stop Microphone
          </button>
        )}
      </div>

      <section className="status-panel" aria-label="Audio pipeline status">
        <h2 className="status-panel-title">Audio Pipeline Diagnostics</h2>

        <div className="status-row">
          <span className="status-label">Microphone</span>
          <span className={`status-value ${mic.className}`}>
            <span className="status-dot" />
            {mic.label}
          </span>
        </div>

        <div className="status-row">
          <span className="status-label">WebSocket Gateway</span>
          <span className={`status-value ${ws.className}`}>
            <span className="status-dot" />
            {ws.label}
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
      </section>

      <p className="hint">
        Audio is processed on a dedicated AudioWorklet thread and streamed as 20 ms binary frames.
      </p>
    </main>
  );
}
