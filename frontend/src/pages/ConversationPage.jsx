/**
 * ConversationPage — main voice conversation interface.
 *
 * Week 1, Day 2: microphone capture → WebSocket streaming (16 kHz Int16LE PCM).
 * Week 1, Day 3: incoming server audio → playback queue → gapless speaker output.
 *
 * The page owns both hooks. It passes the playback queue's enqueue() into
 * startCapture() so the hook wires binary server messages directly to playback
 * without the component needing to inspect each WebSocket event itself.
 */

import { useAudioCapture } from '../hooks/useAudioCapture.js';
import { usePlaybackQueue } from '../hooks/usePlaybackQueue.js';
import './ConversationPage.css';

export default function ConversationPage() {
  // Playback queue: enqueue() accepts an ArrayBuffer and plays it gaplessly.
  const { enqueue, flushPlayback } = usePlaybackQueue();

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
            // Pass enqueue and flushPlayback so server messages are routed correctly.
            onClick={() => startCapture(enqueue, flushPlayback)}
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
