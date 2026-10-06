/**
 * TranscriptView — Displays live speech transcripts and agent responses.
 *
 * Implements real turn display for:
 * - Completed user speech turns
 * - Active partial user speech (in-flight ASR)
 * - Finalized agent responses
 * - Active streaming agent response (in-flight LLM/TTS)
 * - Interrupted agent responses (clearly marked with badge & preserved text)
 * - Thinking state when awaiting model generation
 */

import { useEffect, useRef } from 'react';
import './TranscriptView.css';

function formatTime(timestamp) {
  if (!timestamp) return '';
  const d = new Date(timestamp);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function TranscriptView({
  finalTranscriptEntries = [],
  currentPartialTranscript = null,
  currentAgentPartial = null,
  isCapturing = false,
  turnState = 'idle',
}) {
  const feedEndRef = useRef(null);

  const hasContent =
    finalTranscriptEntries.length > 0 ||
    Boolean(currentPartialTranscript) ||
    Boolean(currentAgentPartial) ||
    (turnState === 'thinking' && isCapturing);

  // Auto-scroll to bottom as new messages arrive
  useEffect(() => {
    if (feedEndRef.current) {
      feedEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [finalTranscriptEntries, currentPartialTranscript, currentAgentPartial, turnState]);

  return (
    <section className="transcript-section" aria-label="Conversation transcript">
      <div className="transcript-header">
        <div className="transcript-title-group">
          <h2 className="transcript-title">Conversation</h2>
          <span className="transcript-count">
            {finalTranscriptEntries.length} {finalTranscriptEntries.length === 1 ? 'turn' : 'turns'}
          </span>
        </div>
        {isCapturing && (
          <span className="transcript-live-badge" title="Session active — listening for speech">
            <span className="transcript-pulse-dot" />
            Live
          </span>
        )}
      </div>

      {!hasContent ? (
        <div className="transcript-empty" id="transcript-empty-state">
          <div className="transcript-empty-icon" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15a3 3 0 01-3-3V4.5a3 3 0 116 0v7.5a3 3 0 01-3 3z" />
            </svg>
          </div>
          <p className="transcript-empty-text">
            No speech detected yet.
          </p>
          <p className="transcript-empty-subtext">
            Connect and speak naturally in Hindi, English, or Hinglish.
          </p>
        </div>
      ) : (
        <div className="transcript-feed" role="log" aria-live="polite">
          {finalTranscriptEntries.map((entry, index) => {
            const isAgent = entry.role === 'agent';
            const isInterrupted = Boolean(entry.interrupted);
            return (
              <div
                key={entry.id || index}
                className={`transcript-message ${isAgent ? 'message-agent' : 'message-user'}${isInterrupted ? ' message-interrupted' : ''}`}
                data-testid={`transcript-${isAgent ? 'agent' : 'user'}-entry`}
              >
                <div className="message-header">
                  <span className="message-sender">{isAgent ? 'Vaani' : 'You'}</span>
                  {isInterrupted && (
                    <span className="badge-interrupted" title="Response was interrupted mid-stream">
                      Interrupted
                    </span>
                  )}
                  {entry.timestamp && (
                    <span className="message-time">{formatTime(entry.timestamp)}</span>
                  )}
                </div>
                <div className="message-body">
                  <p className="message-text">{entry.text}</p>
                </div>
              </div>
            );
          })}

          {/* Active live partial from user */}
          {currentPartialTranscript && (
            <div
              className="transcript-message message-user message-partial"
              data-testid="transcript-partial-entry"
              aria-live="assertive"
            >
              <div className="message-header">
                <span className="message-sender">You</span>
                <span className="message-live-indicator">
                  <span className="partial-pulse-dot" />
                  listening…
                </span>
              </div>
              <div className="message-body">
                <p className="message-text partial-text">{currentPartialTranscript}</p>
              </div>
            </div>
          )}

          {/* Active streaming text from agent */}
          {currentAgentPartial && (
            <div
              className="transcript-message message-agent message-streaming"
              data-testid="transcript-agent-streaming"
              aria-live="assertive"
            >
              <div className="message-header">
                <span className="message-sender">Vaani</span>
                <span className="message-live-indicator">
                  <span className="partial-pulse-dot" />
                  speaking…
                </span>
              </div>
              <div className="message-body">
                <p className="message-text streaming-text">{currentAgentPartial}</p>
              </div>
            </div>
          )}

          {/* Thinking indicator when model is processing before first token arrives */}
          {turnState === 'thinking' && !currentAgentPartial && isCapturing && (
            <div
              className="transcript-message message-agent message-thinking"
              data-testid="transcript-agent-thinking"
              aria-live="polite"
            >
              <div className="message-header">
                <span className="message-sender">Vaani</span>
                <span className="message-live-indicator">
                  <span className="partial-pulse-dot dot-thinking" />
                  thinking…
                </span>
              </div>
              <div className="message-body">
                <div className="thinking-dots">
                  <span className="thinking-dot" />
                  <span className="thinking-dot" />
                  <span className="thinking-dot" />
                </div>
              </div>
            </div>
          )}

          <div ref={feedEndRef} />
        </div>
      )}
    </section>
  );
}

export default TranscriptView;
