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

/** Base URL for the backend API (HTTP). */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * WebSocket URL for the session endpoint (backend/vaani/gateway.py).
 * This is the correct endpoint used from Day 2 onward per docs/contracts.md.
 */
export const WS_SESSION_URL =
  import.meta.env.VITE_WS_SESSION_URL || 'ws://localhost:8000/ws/session';

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
