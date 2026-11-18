/**
 * authApi.js -- the three sign-in calls to the backend (backend/vaani/auth.py).
 *
 * Relative paths ('/auth/me'): the page and the API share ONE origin. In
 * development Vite's dev server answers the page and forwards /auth, /health
 * and /ws to the backend (its proxy, vite.config.js). One origin means the
 * browser sends the vaani_session cookie with these calls by itself
 * (fetch's default, credentials 'same-origin'), and no CORS is involved.
 *
 * Each call resolves to {status, body}; status is null when no answer came
 * (server down, network gone, timed out, aborted). It never throws, so the
 * callers have one path.
 *
 * fetchFn: the fetch to use. Tests pass a fake one (authApi.test.js); the
 * app passes nothing and gets the browser's.
 */

async function call(path, options, fetchFn = fetch) {
  try {
    const res = await fetchFn(path, options);
    // A 204, or the proxy's error page when the backend is down, has no JSON
    // body: keep the status anyway.
    const body = await res.json().catch(() => null);
    return { status: res.status, body };
  } catch {
    return { status: null, body: null };
  }
}

/** GET /auth/me: who the cookie says we are. `signal` aborts the request. */
export function fetchMe({ signal, fetchFn } = {}) {
  return call('/auth/me', { method: 'GET', signal }, fetchFn);
}

/** POST /auth/google: trade Google's ID token for our session cookie. */
export function signInWithGoogle(credential, { fetchFn } = {}) {
  return call('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  }, fetchFn);
}

/** POST /auth/logout: the server answers 204 and deletes the cookie. */
export function logout({ fetchFn } = {}) {
  return call('/auth/logout', { method: 'POST' }, fetchFn);
}
