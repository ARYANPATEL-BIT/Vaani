/**
 * ConversationPage — the main route of the Vaani application.
 *
 * Today this is a placeholder that shows the application name and
 * a status area where microphone and WebSocket diagnostics will
 * appear once Day 2 audio capture is implemented.
 *
 * It does NOT implement audio capture, playback, or WebSocket logic.
 * Those are separate modules that will be wired in on their scheduled days.
 */

import './ConversationPage.css';

export default function ConversationPage() {
  return (
    <main className="conversation-page">
      <h1>Vaani</h1>
      <p className="subtitle">Real-time voice conversation</p>

      <section className="status-panel" aria-label="Connection status">
        <div className="status-row">
          <span className="status-label">Microphone</span>
          <span className="status-value status-idle">Not connected</span>
        </div>
        <div className="status-row">
          <span className="status-label">WebSocket</span>
          <span className="status-value status-idle">Not connected</span>
        </div>
      </section>

      <p className="hint">
        Audio capture and WebSocket transport will be added in Day 2.
      </p>
    </main>
  );
}
