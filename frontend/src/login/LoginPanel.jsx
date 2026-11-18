/**
 * LoginPanel -- the right side of /login: the step label, "Sign in / to go /
 * on air.", then what the current view needs (intro text, the checking line,
 * an alert, or the "Go to the studio" button), Google's button, and three
 * facts.
 *
 * Google's button stays MOUNTED in every view but onair (hidden while
 * checking), so Google draws it once and the refused / error views reuse it
 * as "Use another account" / "Try again": clicking it opens Google's account
 * picker again.
 */

import { Link } from 'react-router-dom';
import GoogleButton from './GoogleButton.jsx';
import { ALERTS, TEXT, VIEWS } from './loginContent.js';

function Alert({ reason, refused }) {
  const a = ALERTS[reason];
  return (
    <div role="alert" className={`lg-alert${refused ? ' lg-alert-refused' : ''}`}>
      <span className="lg-mono lg-alert-tag">{a.tag}</span>
      <p className="lg-cd lg-alert-title">{a.title}</p>
      <p className="lg-alert-text">{a.text}</p>
    </div>
  );
}

// DEV preview only: a look-alike of Google's button, so the layout can be
// checked without a client ID. Not clickable.
function StandIn() {
  return <span className="lg-standin" aria-hidden="true"><span className="lg-standin-g">G</span>Sign in with Google</span>;
}

export default function LoginPanel({ view, reason, name, onCredential, preview }) {
  const v = VIEWS[view];
  const [line1, line2, line3] = TEXT.title;
  return (
    <div className="lg-panel">
      <div className="lg-panel-top">
        <span className="lg-mono lg-step">{v.step}</span>
        <h1 className="lg-cd lg-title">
          {line1}<br />{line2}<br />
          <span className={view === 'onair' ? 'lg-title-lit' : 'lg-outline'}>{line3}</span>
        </h1>

        <div className="lg-action" aria-live="polite">
          {view === 'off' && (
            <p className="lg-intro">
              <span className="lg-wide-only">{TEXT.intro}</span>
              <span className="lg-phone-only">{TEXT.introShort}</span>
            </p>
          )}
          {view === 'checking' && <p className="lg-intro">{TEXT.checking}<span className="lg-blink">…</span></p>}
          {(view === 'refused' || view === 'error') && <Alert reason={reason} refused={view === 'refused'} />}
          {view === 'onair' && (
            <>
              <p className="lg-intro" role="status">
                {TEXT.onAir[0]}<b>{name}</b>{TEXT.onAir[1]}<span className="lg-blink">…</span>
              </p>
              <Link to="/talk" replace className="lg-mono lg-go">
                <span className="lg-go-dot" aria-hidden="true" />{TEXT.goToStudio}
              </Link>
            </>
          )}

          {view !== 'onair' && (
            <div className="lg-signin">
              {view === 'checking' && (
                <button type="button" className="lg-locked" disabled aria-busy="true">{TEXT.checkingButton}</button>
              )}
              {/* hidden, not unmounted, while checking: Google's frame survives. */}
              <div hidden={view === 'checking'}>
                {preview ? <StandIn /> : <GoogleButton onCredential={onCredential} />}
              </div>
              <span className="lg-mono lg-hint">
                <span className={v.hintShort ? 'lg-wide-only' : undefined}>{v.hint}</span>
                {v.hintShort && <span className="lg-phone-only">{v.hintShort}</span>}
              </span>
            </div>
          )}
        </div>
      </div>

      <ol className="lg-mono lg-facts">
        {TEXT.facts.map((fact, i) => (
          <li key={fact}><span className="lg-fact-n">{String(i + 1).padStart(2, '0')}</span><br />{fact}</li>
        ))}
      </ol>
    </div>
  );
}
