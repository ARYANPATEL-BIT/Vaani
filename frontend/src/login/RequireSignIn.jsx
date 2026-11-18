/**
 * RequireSignIn -- the /talk route guard.
 *
 * A route guard is a check that runs when a page is opened and sends the
 * visitor elsewhere if they may not be there. This one draws the page it
 * wraps AT ONCE and asks GET /auth/me in the background. Only a 401 (no
 * valid session cookie) sends the visitor to /login. Signed in, auth off,
 * or no answer: nothing happens, so /talk is never delayed or changed.
 *
 * This is for the visitor's sake, not security: the backend already refuses
 * the /ws/session WebSocket without a valid cookie (auth.py,
 * handshake_refusal). Without the guard, a signed-out visitor would only
 * find out when Connect failed.
 *
 * DEV only: /talk?preview=... is a design preview with no backend, so the
 * guard stays out of its way.
 */

import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchMe } from './authApi.js';
import { meResult } from './loginState.js';

export default function RequireSignIn({ children }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const skip = import.meta.env.DEV && params.has('preview');

  useEffect(() => {
    if (skip) return undefined;
    let alive = true; // a late answer after leaving /talk must not navigate
    fetchMe().then(({ status }) => {
      if (alive && meResult(status) === 'out') navigate('/login', { replace: true });
    });
    return () => { alive = false; };
  }, [skip, navigate]);

  return children;
}
