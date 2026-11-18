/**
 * loginState.js -- what the /login page shows, as a pure function of what
 * the backend answered. No React, no browser, no fetch: node tests it
 * (loginState.test.js).
 *
 * The backend side is backend/vaani/auth.py. Its error bodies look like
 * {"type": "error", "code": "AUTH_NOT_ALLOWED", "message": "..."}.
 *
 * Page views: off (signed out), checking, refused, error, onair.
 * `reason` picks the wording in loginContent.js (ALERTS).
 */

/**
 * The answer to POST /auth/google.
 *
 * @param {number|null} status HTTP status, or null if the request never got
 *                             an answer (server down, network gone)
 * @param {object|null} body   the parsed JSON body, or null
 * @returns {{view: string, reason?: string, name?: string}}
 *          view 'talk' means: auth is off on the server, go straight in.
 */
export function signInResult(status, body) {
  const code = body && typeof body === 'object' ? body.code : undefined;
  if (status === 200) return { view: 'onair', name: firstName(body) };
  // 404: the route exists only when [auth] enabled is true (auth.py).
  if (status === 404) return { view: 'talk' };
  if (status === 403 && code === 'AUTH_NOT_ALLOWED') return { view: 'refused', reason: 'notAllowed' };
  if (status === 403 && code === 'AUTH_EMAIL_UNVERIFIED') return { view: 'refused', reason: 'unverified' };
  if (status === 403 && code === 'AUTH_BAD_ORIGIN') return { view: 'error', reason: 'badOrigin' };
  if (status === 401 && code === 'AUTH_INVALID_TOKEN') return { view: 'error', reason: 'invalidToken' };
  if (status === 503) return { view: 'error', reason: 'googleDown' };
  // No answer at all, or one we do not know: the server is the problem.
  return { view: 'error', reason: 'serverDown' };
}

/**
 * The answer to GET /auth/me.
 *   200 {email, name}  -> 'in'      (a valid session cookie)
 *   200 {email: null}  -> 'in'      (auth is off on the server: everyone is in)
 *   401                -> 'out'
 *   anything else      -> 'unknown' (server down: do not guess)
 */
export function meResult(status) {
  if (status === 200) return 'in';
  if (status === 401) return 'out';
  return 'unknown';
}

/** "Samyak Raj Singh" -> "Samyak". Falls back to the email, then "". */
export function firstName(body) {
  const name = body && typeof body.name === 'string' ? body.name.trim() : '';
  if (name) return name.split(/\s+/)[0];
  return body && typeof body.email === 'string' ? body.email : '';
}
