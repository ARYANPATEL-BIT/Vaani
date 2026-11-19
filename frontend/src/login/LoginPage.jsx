/**
 * LoginPage -- /login, the "studio door" (docs/design/login-studio-door/).
 *
 * The flow:
 *   1. On load, GET /auth/me. Already signed in, or auth off on the server:
 *      go to /talk. Signed out, or no answer: stay and show the door.
 *   2. The user picks an account in Google's button. Google hands us an ID
 *      token; the view becomes "checking" and the button is locked.
 *   3. POST /auth/google with that token. loginState.js turns the answer
 *      into the next view: onair, refused or error (or straight to /talk if
 *      the server says auth is off).
 *   4. onair: after LOGIN_ONAIR_HOLD_MS the page opens /talk by itself;
 *      "Go to the studio" goes sooner. Reduced motion stops the glow and the
 *      bars (CSS) but not the move.
 *
 * The cookie the backend sets is httpOnly: this page cannot read it, and
 * does not need to. It only reads the status codes.
 */

import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { LOGIN_ONAIR_HOLD_MS } from '../config.js';
import useIstClock from '../landing/useIstClock.js';
import { fetchMe, signInWithGoogle } from '../api/authApi.js';
import { meResult, signInResult } from './loginState.js';
import { previewFor } from './loginPreview.js';
import { ALERTS, INK, PAPER, TEXT } from './loginContent.js';
import StudioDoor from './StudioDoor.jsx';
import LoginPanel from './LoginPanel.jsx';
import './login.css';

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // DEV only: in a production build this whole expression is `null`.
  const preview = import.meta.env.DEV ? previewFor(params.get('preview')) : null;
  const [state, setState] = useState({ view: 'off' });
  const shown = preview ?? state;
  const time = useIstClock();
  // The app's theme, set on <html> before React loaded (index.html). /login
  // has no theme toggle, so reading it once per render is enough.
  const dark = document.documentElement.dataset.theme === 'dark';

  // 1. Already in? `alive` stops a late answer from navigating after the
  // user has left the page.
  useEffect(() => {
    if (preview) return undefined;
    let alive = true;
    fetchMe().then(({ status }) => {
      if (alive && meResult(status) === 'in') navigate('/talk', { replace: true });
    });
    return () => { alive = false; };
  }, [preview, navigate]);

  // 2 + 3. Google's callback. The state check is the "locked" guarantee:
  // Google's button is hidden while checking, so a second token cannot come.
  const onCredential = useCallback(async (credential) => {
    setState({ view: 'checking' });
    const { status, body } = await signInWithGoogle(credential);
    const next = signInResult(status, body);
    if (next.view === 'talk') navigate('/talk', { replace: true });
    else setState(next);
  }, [navigate]);

  // 4. On air: open the studio after the hold. Cleared if the page unmounts
  // first (the user clicked "Go to the studio").
  useEffect(() => {
    if (preview || state.view !== 'onair') return undefined;
    const id = setTimeout(() => navigate('/talk', { replace: true }), LOGIN_ONAIR_HOLD_MS);
    return () => clearTimeout(id);
  }, [preview, state.view, navigate]);

  return (
    <div className="lg" style={dark ? INK : PAPER}>
      <svg className="lg-grain" aria-hidden="true">
        <filter id="lg-grain-f"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" /></filter>
        <rect width="100%" height="100%" filter="url(#lg-grain-f)" />
      </svg>
      <header className="lg-header">
        <Link to="/" className="lg-brand" aria-label="Vaani home">
          <span className="lg-dv lg-brand-dv" aria-hidden="true">वाणी</span>
          <span className="lg-cd lg-brand-name" aria-hidden="true">Vaani<span className="lg-red">.</span></span>
        </Link>
        <span className="lg-mono lg-file lg-wide-only">{TEXT.file}</span>
        <div className="lg-mono lg-header-end">
          <Link to="/" className="lg-back">
            <span className="lg-wide-only">{TEXT.back}</span>
            <span className="lg-phone-only">{TEXT.backShort}</span>
          </Link>
          <span className="lg-wide-only">{TEXT.clock} {time}</span>
        </div>
      </header>
      <main className="lg-main">
        <StudioDoor view={shown.view} doorStatus={ALERTS[shown.reason]?.door} />
        <LoginPanel view={shown.view} reason={shown.reason} name={shown.name}
          onCredential={onCredential} preview={Boolean(preview)} />
      </main>
      <footer className="lg-mono lg-footer lg-wide-only">
        <span>{TEXT.footer[0]}</span>
        <span>{TEXT.footer[1]}</span>
      </footer>
    </div>
  );
}
