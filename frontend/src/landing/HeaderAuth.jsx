/**
 * HeaderAuth -- the landing header's sign-in corner: a Sign in link, or the
 * signed-in first name with a Log out button, or nothing (auth off).
 *
 * `auth` comes from landingAuthFor (login/loginState.js); Hero.jsx owns it
 * and passes `onLogOut`. A plain component with no fetching of its own, so
 * headerAuth.test.js can render it in Node for each state.
 */

import { Link } from 'react-router-dom';
import { HERO } from './landingContent.js';

export default function HeaderAuth({ auth, onLogOut }) {
  return (
    <>
      {auth.who && (
        <span className="lp-mono lp-onair">
          <span className="lp-sr">{HERO.signedInAs} </span>{auth.who}
        </span>
      )}
      {auth.logOut && (
        <button type="button" className="lp-mono lp-outline-pill lp-button-pill" onClick={onLogOut}>
          {HERO.logOut}
        </button>
      )}
      {auth.signIn && <Link to="/login" className="lp-mono lp-outline-pill">{HERO.signIn}</Link>}
    </>
  );
}
