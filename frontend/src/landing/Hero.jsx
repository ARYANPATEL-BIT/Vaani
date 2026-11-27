/**
 * Hero -- the header ("On air" clock, Sign in or the signed-in name, Open
 * the app), the headline "TALK OVER IT." whose letters rise one by one, the
 * description, the Start talking pill, the live tape and the spec strip.
 */

import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { APP_PATH, CLOCK, HERO, SPECS } from './landingContent.js';
import { VaaniLogo } from '../components/brand/VaaniLogo.jsx';
import { AUTH_CHECK_TIMEOUT_MS } from '../config.js';
import { fetchMe, logout } from '../api/authApi.js';
import { landingAuthFor, logOutFromLanding } from '../login/loginState.js';
import HeaderAuth from './HeaderAuth.jsx';
import useIstClock from './useIstClock.js';
import LiveTape from './LiveTape.jsx';
import Arrow from './Arrow.jsx';

// Each letter gets its position in the whole headline (--i): CSS delays its
// rise by --i steps. Each word is one unbreakable box, so the headline only
// ever wraps between words, never inside one.
let letterCount = 0;
const HEADLINE = HERO.headline.map((word) => ({
  word,
  letters: [...word].map((ch) => ({ ch, i: letterCount++, red: HERO.redChars.includes(ch) })),
}));

export default function Hero({ reducedMotion, leadS, paused, onTogglePause }) {
  const clock = useIstClock();
  // Starts as "nothing extra", so the header draws at once, exactly as it
  // did before sign-in existed. The landing page is public and never waits
  // on the backend: /auth/me only ever ADDS a Sign in link, or a name and
  // Log out.
  const [auth, setAuth] = useState({ signIn: false, who: '', logOut: false });
  const navigate = useNavigate();

  useEffect(() => {
    // Two ways to stop the request, merged into one signal (as in
    // login/requireSignIn.js): the page unmounting (the visitor left), or
    // the backend hanging past AUTH_CHECK_TIMEOUT_MS. fetchMe never throws;
    // an aborted call comes back as {status: null}, which means "nothing extra".
    const leaving = new AbortController();
    const signal = AbortSignal.any([leaving.signal, AbortSignal.timeout(AUTH_CHECK_TIMEOUT_MS)]);
    fetchMe({ signal }).then(({ status, body }) => {
      if (!leaving.signal.aborted) setAuth(landingAuthFor(status, body));
    });
    return () => leaving.abort();
  }, []);

  // Log out, then back to the top of the landing page, showing whatever
  // the server now says (logOutFromLanding). The sidebar's Logout
  // (useSignOut) is separate and still goes to /login.
  const onLogOut = useCallback(async () => {
    setAuth(await logOutFromLanding(logout, fetchMe));
    navigate('/', { replace: true });
    window.scrollTo(0, 0);
  }, [navigate]);

  return (
    <>
      <header className="lp-header lp-wrap">
        <a href="#top" className="lp-brand" aria-label={HERO.backToTop}>
          <VaaniLogo height={36} ink="var(--lp-ink)" paper="var(--lp-paper)" />
        </a>
        <div className="lp-header-right">
          <span className="lp-mono lp-onair">
            <span className="lp-dot lp-blink" aria-hidden="true" />
            {HERO.onAir} &middot; {CLOCK.label} {clock}
          </span>
          <HeaderAuth auth={auth} onLogOut={onLogOut} />
          <Link to={APP_PATH} className="lp-mono lp-outline-pill">{HERO.openApp}</Link>
        </div>
      </header>

      <section className="lp-hero lp-wrap" aria-labelledby="lp-hero-title">
        <div className="lp-mono lp-hero-meta">
          <span>{HERO.fileLabel}</span>
          <span>{HERO.languages}</span>
        </div>
        <h1 id="lp-hero-title" className="lp-cd lp-headline">
          {/* Screen readers read this one plain sentence; the animated
              letters below are hidden from them. */}
          <span className="lp-sr">{HERO.headlineSpoken}</span>
          {HEADLINE.map(({ word, letters }) => (
            <span key={word} className="lp-hword" aria-hidden="true">
              {letters.map((l) => (
                <span key={l.i} className="lp-lm">
                  <span className={l.red ? 'lp-red-text' : undefined} style={{ '--i': l.i }}>{l.ch}</span>
                </span>
              ))}
            </span>
          ))}
        </h1>
        <div className="lp-hero-row">
          <p className="lp-hero-desc">{HERO.description}</p>
          <Link to={APP_PATH} className="lp-mono lp-pill lp-pill-lg">{HERO.cta}<Arrow /></Link>
        </div>

        <LiveTape reducedMotion={reducedMotion} leadS={leadS} paused={paused} onTogglePause={onTogglePause} />

        <dl className="lp-specs">
          {SPECS.map((s) => (
            <div key={s.label} className="lp-spec">
              <dt className="lp-mono">{s.label}</dt>
              <dd className="lp-cd">
                {s.num}<span className="lp-mono lp-spec-unit">{s.unit}</span>
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  );
}
