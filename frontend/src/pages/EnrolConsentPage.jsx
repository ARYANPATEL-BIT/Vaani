/**
 * EnrolConsentPage — Explains the reference-voice recording process and
 * requires explicit user acknowledgement before proceeding.
 *
 * Scope (Week 3 Day 3):
 *  - Describes what the reference recording is and why it is needed.
 *  - Lists recording guidance (quiet room, speak normally, 30–60 s).
 *  - Requires a checkbox acknowledgement.
 *  - Offers Continue (→ /enrol/record) and Cancel (→ /) actions.
 *  - Makes no backend calls; no data is sent from this screen.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic, Shield, Clock, Volume2, CheckCircle2, ArrowRight, X } from 'lucide-react';
import './EnrolConsentPage.css';

const GUIDANCE_ITEMS = [
  {
    icon: Volume2,
    title: 'Find a quiet spot',
    body: 'Background noise will reduce accuracy. A room with minimal echo works best.',
  },
  {
    icon: Mic,
    title: 'Speak naturally',
    body: 'Talk at your normal pace and volume. You can say anything — read a passage, describe your day, or count to 100.',
  },
  {
    icon: Clock,
    title: '30 to 60 seconds',
    body: 'The recording must be at least 30 seconds. It will stop automatically at 60 seconds.',
  },
  {
    icon: Shield,
    title: 'Stored in your browser only',
    body: 'Your voice recording stays in this browser session and is not uploaded to any server during this step.',
  },
];

export default function EnrolConsentPage() {
  const navigate = useNavigate();
  const [acknowledged, setAcknowledged] = useState(false);

  return (
    <main className="consent-page" aria-labelledby="consent-title">
      <div className="consent-card">
        {/* Header */}
        <div className="consent-header">
          <div className="consent-icon-wrap" aria-hidden="true">
            <Mic size={28} strokeWidth={1.7} />
          </div>
          <div>
            <h1 id="consent-title" className="consent-title">
              Record Your Reference Voice
            </h1>
            <p className="consent-subtitle">
              Vaani uses a short voice sample to personalise your experience.
            </p>
          </div>
        </div>

        {/* Purpose explanation */}
        <section className="consent-section" aria-labelledby="consent-purpose-heading">
          <h2 id="consent-purpose-heading" className="consent-section-heading">
            Why we need this
          </h2>
          <p className="consent-body-text">
            Your reference recording lets Vaani identify when you are speaking so it
            can respond only to you. The sample is kept in your browser memory for
            this session and is never uploaded or shared in this step.
          </p>
        </section>

        {/* Recording guidance */}
        <section className="consent-section" aria-labelledby="consent-guidance-heading">
          <h2 id="consent-guidance-heading" className="consent-section-heading">
            Before you start
          </h2>
          <ul className="consent-guidance-list" role="list">
            {GUIDANCE_ITEMS.map(({ icon: Icon, title, body }) => (
              <li key={title} className="guidance-item">
                <span className="guidance-icon" aria-hidden="true">
                  <Icon size={18} strokeWidth={1.8} />
                </span>
                <div>
                  <span className="guidance-title">{title}</span>
                  <span className="guidance-body">{body}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Duration callout */}
        <div className="consent-duration-callout" role="note">
          <Clock size={16} strokeWidth={2} aria-hidden="true" />
          <span>
            <strong>Duration:</strong> 30 seconds minimum · 60 seconds maximum
          </span>
        </div>

        {/* Acknowledgement */}
        <label className="consent-ack-label" htmlFor="consent-ack-checkbox">
          <input
            id="consent-ack-checkbox"
            type="checkbox"
            className="consent-ack-checkbox"
            checked={acknowledged}
            onChange={e => setAcknowledged(e.target.checked)}
            aria-describedby="consent-ack-description"
          />
          <span id="consent-ack-description" className="consent-ack-text">
            I understand that my voice will be recorded for 30–60 seconds and stored
            locally in this browser session only.
          </span>
          {acknowledged && (
            <CheckCircle2
              size={18}
              strokeWidth={2}
              className="consent-ack-check-icon"
              aria-hidden="true"
            />
          )}
        </label>

        {/* Actions */}
        <div className="consent-actions">
          <button
            id="consent-cancel-btn"
            type="button"
            className="consent-btn consent-btn-secondary"
            onClick={() => navigate('/')}
            aria-label="Cancel and return to conversation"
          >
            <X size={16} strokeWidth={2} />
            Cancel
          </button>
          <button
            id="consent-continue-btn"
            type="button"
            className="consent-btn consent-btn-primary"
            onClick={() => navigate('/enrol/record')}
            disabled={!acknowledged}
            aria-disabled={!acknowledged}
            aria-label="Continue to voice recording"
          >
            Continue
            <ArrowRight size={16} strokeWidth={2} />
          </button>
        </div>
      </div>
    </main>
  );
}
