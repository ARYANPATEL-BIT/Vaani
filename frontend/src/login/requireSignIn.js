/**
 * requireSignIn.js -- the route gate, as a React Router LOADER.
 *
 * A loader is a function the router runs, and waits for, BEFORE it shows a
 * route. router.jsx gives this one to /talk and to the sidebar layout (the
 * enrol pages, /loopback, the 404 page). So a signed-out visitor never sees
 * those pages at all: the router gets the redirect first and opens /login.
 *
 *   GET /auth/me answers 401        -> throw redirect('/login')
 *   200 {email, name}               -> return it (the page shows the name)
 *   200 {email: null, name: null}   -> auth is off on the server: return it
 *   no answer / 5xx / timed out     -> let the visitor in, as nobody. We do
 *                                      not guess "signed out" from a broken
 *                                      server; the socket's own error says
 *                                      what is wrong.
 *
 * This is for the visitor's sake, not security: the backend refuses the
 * /ws/session handshake without a valid cookie anyway (auth.py).
 *
 * Two ways the check can be cut short, combined into one signal:
 *   - the router's `signal` aborts when the visitor navigates away mid-check;
 *   - AbortSignal.timeout(timeoutMs) aborts a hung /auth/me, so the page is
 *     never left blank waiting for it.
 * AbortSignal.any() makes a signal that aborts when EITHER of them does.
 */

import { redirect } from 'react-router-dom';
import { fetchMe } from '../api/authApi.js';
import { meResult } from './loginState.js';

/** What a page gets when nobody is signed in but the gate let them in. */
export const NO_USER = { email: null, name: null };

export async function requireSignIn({ signal, timeoutMs, fetchFn }) {
  const both = AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]);
  const { status, body } = await fetchMe({ signal: both, fetchFn });
  // Thrown, not returned: React Router treats a thrown Response from a
  // loader as "go there instead" and never renders this route.
  if (meResult(status) === 'out') throw redirect('/login');
  return status === 200 && body ? { email: body.email, name: body.name } : NO_USER;
}
