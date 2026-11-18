/**
 * loginPreview.js -- DEVELOPMENT ONLY. Lets every /login state be checked
 * without a Google client ID or a backend:
 *   /login?preview=off | checking | refused | error | onair
 * (off is the plain signed-out page, without the /auth/me check that sends
 * you on to /talk when the local backend runs with auth turned off).
 *
 * LoginPage.jsx calls previewFor() only inside `import.meta.env.DEV ? ... :
 * null`, so a production build drops this module, like talk/studioPreview.js.
 * In a preview the page makes no request and never leaves the page.
 */

const SCENES = {
  off: { view: 'off' },
  checking: { view: 'checking' },
  refused: { view: 'refused', reason: 'notAllowed' },
  error: { view: 'error', reason: 'googleDown' },
  onair: { view: 'onair', name: 'Samyak' },
};

/** The state for ?preview=<name>, or null. */
export function previewFor(name) {
  return SCENES[name] ?? null;
}
