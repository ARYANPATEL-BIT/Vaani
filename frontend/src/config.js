/**
 * Frontend configuration for the Vaani application.
 *
 * All configurable values live here — no hardcoded constants scattered
 * across components. Values that differ between development and production
 * are read from Vite environment variables (import.meta.env).
 *
 * Audio parameters mirror backend/config.toml so the two sides agree.
 */

// --- Server connection ---

// The page and the backend share ONE origin: every backend URL is relative to
// the page. In development Vite's dev server forwards /auth, /health and /ws
// to the backend (the proxy in vite.config.js; its target is
// VAANI_PROXY_TARGET). So nothing here names a host or a port.

/**
 * The WebSocket URL of the session endpoint (backend/vaani/gateway.py), on
 * the page's own host. ws: on an http page, wss: (encrypted) on an https page
 * such as a Cloudflare tunnel: a browser refuses plain ws: from https.
 */
export function sessionSocketUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${window.location.host}/ws/session`;
}

// --- Sign-in (src/login/, backend/vaani/auth.py) ---

/**
 * The Google OAuth client ID our sign-in button is for. Must be the SAME ID
 * as the backend's VAANI_AUTH__GOOGLE_CLIENT_ID, or the backend rejects the
 * token (wrong audience). Empty: /login shows a message instead of a button.
 * A client ID is public (Google shows it in every sign-in page), not a secret.
 */
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

/** Google Identity Services: the script that draws Google's own button. */
export const GIS_SCRIPT_URL = 'https://accounts.google.com/gsi/client';

/** How long the lit "On air" lamp shows after sign-in before /talk opens. */
export const LOGIN_ONAIR_HOLD_MS = 1500;

/**
 * The longest the route gate (login/requireSignIn.js) waits for GET
 * /auth/me before letting the visitor in anyway. A blank page while the
 * server hangs is worse than the socket's own error a moment later.
 */
export const AUTH_CHECK_TIMEOUT_MS = 5000;

// --- Audio parameters (must match backend/config.toml) ---

/** Target sample rate in Hz. Speech models expect 16 kHz. */
export const AUDIO_SAMPLE_RATE = 16_000;

/** Duration of one audio frame in milliseconds. */
export const AUDIO_FRAME_MS = 20;

/**
 * Number of mono samples in one frame.
 * 16 000 samples/s × 0.020 s = 320 samples.
 */
export const AUDIO_FRAME_SAMPLES = AUDIO_SAMPLE_RATE * (AUDIO_FRAME_MS / 1000);

// --- Push-to-talk (docs/contracts.md §2.8) ---

/**
 * How long, after stop is pressed, to wait for the AudioWorklet to hand over
 * the press's last frame before sending ptt.end anyway (src/ptt/pttPress.js).
 * The worklet answers within one render quantum (8 ms at 16 kHz) when the
 * audio thread is running; 300 ms only matters if that thread has stalled.
 */
export const PTT_END_FALLBACK_MS = 300;
