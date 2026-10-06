/**
 * Transcript — scrollable chat bubble list.
 *
 * Renders:
 * - Finalized user turns (role: 'user')
 * - Finalized agent turns (role: 'agent')
 * - Live partial user speech
 * - Live streaming agent reply (animated dots)
 * - Empty state
 */

import { useEffect, useRef } from 'react';
import { PlayCircle, MoreVertical } from 'lucide-react';
import './Transcript.css';

function fmt(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function UserBubble({ text, timestamp }) {
  return (
    <div className="bubble-row bubble-user">
      <div className="bubble-avatar avatar-user">You</div>
      <div className="bubble-col">
        <div className="bubble-meta">
          <span className="bubble-name name-user">You</span>
          <span className="bubble-time">{fmt(timestamp)}</span>
        </div>
        <div className="bubble bubble-user-card">
          <p className="bubble-text">{text}</p>
        </div>
      </div>
    </div>
  );
}

function AgentBubble({ text, timestamp }) {
  return (
    <div className="bubble-row bubble-agent">
      <div className="bubble-avatar avatar-vaani">
        <div className="vaani-avatar-icon">
          <span className="vaani-dot" />
          <span className="vaani-dot" />
          <span className="vaani-dot" />
        </div>
      </div>
      <div className="bubble-col">
        <div className="bubble-meta">
          <span className="bubble-name name-vaani">Vaani</span>
          <span className="bubble-time">{fmt(timestamp)}</span>
        </div>
        <div className="bubble bubble-vaani-card">
          <p className="bubble-text">{text}</p>
          <div className="bubble-actions">
            <button className="bubble-btn" aria-label="Play message">
              <PlayCircle size={18} strokeWidth={1.8} />
            </button>
            <button className="bubble-btn" aria-label="More options">
              <MoreVertical size={18} strokeWidth={1.8} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PartialUserBubble({ text }) {
  return (
    <div className="bubble-row bubble-user">
      <div className="bubble-avatar avatar-user">You</div>
      <div className="bubble-col">
        <div className="bubble-meta">
          <span className="bubble-name name-user">You</span>
          <span className="bubble-time live-label">
            <span className="micro-dot" />listening…
          </span>
        </div>
        <div className="bubble bubble-user-card bubble-partial">
          <p className="bubble-text">{text}</p>
        </div>
      </div>
    </div>
  );
}

function StreamingAgentBubble() {
  return (
    <div className="bubble-row bubble-agent">
      <div className="bubble-avatar avatar-vaani">
        <div className="vaani-avatar-icon">
          <span className="vaani-dot" />
          <span className="vaani-dot" />
          <span className="vaani-dot" />
        </div>
      </div>
      <div className="bubble-col">
        <div className="bubble-meta">
          <span className="bubble-name name-vaani">Vaani</span>
          <span className="bubble-time live-label">
            <span className="micro-dot green" />speaking…
          </span>
        </div>
        <div className="bubble bubble-vaani-card bubble-typing">
          <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
        </div>
      </div>
    </div>
  );
}

function EmptyState({ isConnected }) {
  return (
    <div className="transcript-empty">
      <div className="empty-icon">🎙️</div>
      <p className="empty-title">
        {isConnected ? 'Start speaking…' : 'Ready to listen'}
      </p>
      <p className="empty-sub">
        {isConnected
          ? 'Your conversation will appear here.'
          : 'Connect and start your conversation in Hindi, English, or Hinglish.'}
      </p>
    </div>
  );
}

export default function Transcript({
  finalTranscriptEntries = [],
  currentPartialTranscript = null,
  currentAgentPartial = null,
  isConnected = false,
}) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [finalTranscriptEntries.length, currentPartialTranscript, currentAgentPartial]);

  const hasContent = finalTranscriptEntries.length > 0
    || Boolean(currentPartialTranscript)
    || Boolean(currentAgentPartial);

  return (
    <div className="transcript-scroll" role="log" aria-live="polite">
      {!hasContent ? (
        <EmptyState isConnected={isConnected} />
      ) : (
        <div className="transcript-messages">
          {finalTranscriptEntries.map((entry) =>
            entry.role === 'agent'
              ? <AgentBubble key={entry.id} text={entry.text} timestamp={entry.timestamp} />
              : <UserBubble  key={entry.id} text={entry.text} timestamp={entry.timestamp} />
          )}

          {currentPartialTranscript && (
            <PartialUserBubble text={currentPartialTranscript} />
          )}

          {currentAgentPartial && <StreamingAgentBubble />}

          <div ref={endRef} />
        </div>
      )}
    </div>
  );
}
