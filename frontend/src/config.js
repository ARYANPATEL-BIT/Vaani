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

/** WebSocket URL for the real-time audio channel. */
export const WS_URL =
  import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/audio';

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
