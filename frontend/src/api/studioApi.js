/**
 * studioApi.js -- the calls to the voice studio (studio/voice_studio/, a
 * separate server on its own port; routes in docs/contracts.md section 4).
 *
 * Relative paths ('/studio/...'): Vite forwards /studio to the studio
 * process (vite.config.js), so the page, the backend and the studio share
 * ONE origin. The browser therefore sends the vaani_session cookie with
 * these calls by itself, and the studio checks it exactly as the backend does.
 *
 * Every call resolves to { status, body, error } and never throws:
 *   status  the HTTP status, or null when no answer came at all;
 *   body    the parsed JSON (or, for generate, { blob, generationId });
 *   error   a sentence for the user when the call did not succeed. The
 *           studio writes its refusals for the user already ("too noisy:
 *           move to a quiet room..."), so its own message is used as is.
 *
 * fetchFn: tests pass a fake fetch (studioApi.test.js); the app passes none.
 */

export const STUDIO_DOWN =
  'The voice studio is not running. Start it (studio/, see the learning document 25) and reload.';

async function call(path, options, fetchFn = fetch) {
  let res;
  try {
    res = await fetchFn(path, options);
  } catch (err) {
    // An abort is the user's own cancel, not a failure to report.
    if (err?.name === 'AbortError') return { status: null, body: null, error: null };
    return { status: null, body: null, error: STUDIO_DOWN };
  }
  const body = await res.json().catch(() => null);
  // Every studio route answers JSON. A 200 without it is someone else's page:
  // the deployed backend (feat/render-deploy) serves the app's HTML for any
  // unknown GET path, and no studio runs there.
  if (res.ok && body === null) return { status: res.status, body: null, error: STUDIO_DOWN };
  return { status: res.status, body, error: res.ok ? null : describe(res.status, body) };
}

/** The user-facing sentence for a failed answer. */
export function describe(status, body) {
  if (body?.message) return body.message;
  // No JSON at all: Vite's proxy answers 500/502/504 itself when nothing
  // listens on the studio's port.
  if (status >= 500) return STUDIO_DOWN;
  return `The studio answered ${status}.`;
}

/** GET /studio/voice: enrolled or not, the consent text, the limits. */
export function fetchVoice({ fetchFn } = {}) {
  return call('/studio/voice', { method: 'GET' }, fetchFn);
}

/** POST /studio/challenge: a fresh random phrase to read aloud. */
export function newChallenge({ fetchFn } = {}) {
  return call('/studio/challenge', { method: 'POST' }, fetchFn);
}

/**
 * POST /studio/enrol: the voice sample, the challenge recording and the
 * consent text, as one multipart form. `sampleName` keeps an uploaded
 * file's extension, which tells the server's decoder what the bytes are.
 */
export function enrol({ sample, sampleName, challenge, consentText }, { fetchFn } = {}) {
  const form = new FormData();
  form.append('sample', sample, sampleName);
  form.append('challenge', challenge, 'challenge.webm');
  form.append('consent_text', consentText);
  return call('/studio/enrol', { method: 'POST', body: form }, fetchFn);
}

/**
 * POST /studio/generate: the script, answered with a WAV. `signal` is the
 * cancellation: aborting it closes the request, the studio notices the
 * disconnect and stops before the next sentence.
 */
export async function generate(script, { signal, fetchFn = fetch } = {}) {
  let res;
  try {
    res = await fetchFn('/studio/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
      signal,
    });
  } catch (err) {
    if (err?.name === 'AbortError') return { status: null, body: null, error: null };
    return { status: null, body: null, error: STUDIO_DOWN };
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    return { status: res.status, body, error: describe(res.status, body) };
  }
  const blob = await res.blob();
  return {
    status: res.status,
    body: { blob, generationId: res.headers.get('X-Generation-Id') },
    error: null,
  };
}

/** DELETE /studio/voice: the sample, embedding, consent and all generated audio. */
export function deleteVoice({ fetchFn } = {}) {
  return call('/studio/voice', { method: 'DELETE' }, fetchFn);
}
