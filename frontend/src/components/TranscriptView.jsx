/**
 * TranscriptView — Displays live speech transcripts for the active conversation.
 *
 * Implements the two distinct visual states:
 * 1. Finalized transcript entries: permanent, fixed in place, styled as completed turns.
 * 2. Active partial transcript: live updating speech in progress, styled with
 *    an active indicator to signal that recognition is ongoing.
 *
 * Handles:
 * - Empty state when no speech has occurred yet
 * - Single partial update
 * - In-place partial replacement (no multiple messages created)
 * - Finalized turns remaining immutable while next partial appears
 */

import './TranscriptView.css';

/**
 * Format Unix timestamp to local HH:MM:SS format for turn metadata.
 */
function formatTime(timestamp) {
  if (!timestamp) return '';
  const d = new Date(timestamp);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function TranscriptView({
  finalTranscriptEntries = [],
  currentPartialTranscript = null,
  isCapturing = false,
}) {
  const hasContent = finalTranscriptEntries.length > 0 || Boolean(currentPartialTranscript);

  return (
    <section className="transcript-section" aria-label="Conversation transcript">
      <div className="transcript-header">
        <h2 className="transcript-title">Transcript</h2>
        {isCapturing && (
          <span className="transcript-live-badge" title="Session active — listening for speech">
            <span className="transcript-pulse-dot" />
            Live
          </span>
        )}
      </div>

      {!hasContent ? (
        <div className="transcript-empty" id="transcript-empty-state">
          <p className="transcript-empty-text">
            No speech detected yet. Connect and speak to see live transcription.
          </p>
        </div>
      ) : (
        <div className="transcript-feed" role="log" aria-live="polite">
          {finalTranscriptEntries.map((entry, index) => (
            <div
              key={entry.id || index}
              className="transcript-entry transcript-final"
              data-testid="transcript-final-entry"
            >
              <div className="transcript-entry-meta">
                <span className="transcript-tag tag-final">Final</span>
                {entry.timestamp && (
                  <span className="transcript-timestamp">{formatTime(entry.timestamp)}</span>
                )}
              </div>
              <p className="transcript-text">{entry.text}</p>
            </div>
          ))}

          {currentPartialTranscript && (
            <div
              className="transcript-entry transcript-partial"
              data-testid="transcript-partial-entry"
              aria-live="assertive"
            >
              <div className="transcript-entry-meta">
                <span className="transcript-tag tag-partial">
                  <span className="partial-pulse-dot" />
                  Listening…
                </span>
              </div>
              <p className="transcript-text transcript-partial-text">
                {currentPartialTranscript}
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default TranscriptView;
