/**
 * authApi.js -- the three sign-in calls to the backend (backend/vaani/auth.py).
 *
 * credentials: 'include' on every call. The page runs on :5173 and the API
 * on :8000, which the browser treats as two different origins. Without
 * 'include', a cross-origin fetch neither stores the Set-Cookie it gets back
 * nor sends the cookie it already has. The backend's CORS settings
 * (allow_credentials, an exact origin list) are what let it through.
 *
 * Each call resolves to {status, body}; status is null when no answer came
 * (server down, network gone). It never throws, so the page has one path.
 */

import { API_BASE_URL } from '../config.js';

async function call(path, options) {
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', ...options });
    // A 204 or a non-JSON error page has no JSON body: keep the status anyway.
    const body = await res.json().catch(() => null);
    return { status: res.status, body };
  } catch {
    return { status: null, body: null };
  }
}

/** GET /auth/me: who the cookie says we are. */
export function fetchMe() {
  return call('/auth/me', { method: 'GET' });
}

/** POST /auth/google: trade Google's ID token for our session cookie. */
export function signInWithGoogle(credential) {
  return call('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  });
}

/** POST /auth/logout: the server answers 204 and deletes the cookie. */
export function logout() {
  return call('/auth/logout', { method: 'POST' });
}
