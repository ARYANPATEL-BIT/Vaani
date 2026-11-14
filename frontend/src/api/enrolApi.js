/**
 * enrolApi.js — API client for the Vaani voice enrolment endpoints.
 *
 * Week 4 Day 1: Connects the enrolment frontend to Aryan's backend API.
 *
 * Endpoints consumed (from docs/contracts.md §3, Planned):
 *   POST /api/enrol/upload   — upload reference audio for validation
 *   GET  /api/enrol/status/:enrolmentId — poll validation status
 *
 * Note: As of Week 4 Day 1, the backend enrolment endpoints are listed as
 * "Planned" in docs/contracts.md §3. This client is built to match the
 * expected contract. If the backend returns 404 or is unavailable, the
 * errors are surfaced honestly to the user — no mock responses are used.
 *
 * Error handling:
 *   - Network errors (fetch throws): caught and returned as { ok: false, error, networkError: true }
 *   - HTTP errors (non-2xx): body parsed if JSON, returned as { ok: false, error, httpStatus }
 *   - Timeouts: AbortController with configurable timeout
 *   - Malformed responses: caught and returned as { ok: false, error }
 */

import { API_BASE_URL } from '../config.js';

/** Default timeout for API requests in milliseconds. */
const DEFAULT_TIMEOUT_MS = 30_000;

/** Polling interval for status checks in milliseconds. */
export const STATUS_POLL_INTERVAL_MS = 2_000;

/** Maximum number of polling attempts before giving up. */
export const MAX_POLL_ATTEMPTS = 60; // 2 minutes at 2s intervals

/**
 * Upload reference audio to the backend for enrolment validation.
 *
 * Sends the recorded audio blob as multipart/form-data.
 * The backend is expected to accept the file and return an enrolment ID
 * for status polling.
 *
 * @param {Blob} audioBlob — The recorded reference audio (webm/opus).
 * @param {object} [options]
 * @param {string} [options.userId] — User identifier (optional, for future use).
 * @param {number} [options.timeoutMs] — Request timeout in ms.
 * @param {AbortSignal} [options.signal] — External abort signal.
 * @returns {Promise<{
 *   ok: boolean,
 *   enrolmentId?: string,
 *   status?: string,
 *   error?: string,
 *   httpStatus?: number,
 *   networkError?: boolean,
 *   serverUnavailable?: boolean,
 * }>}
 */
export async function uploadEnrolmentAudio(audioBlob, options = {}) {
  const {
    userId = 'default',
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal: externalSignal,
  } = options;

  if (!audioBlob || !(audioBlob instanceof Blob) || audioBlob.size === 0) {
    return { ok: false, error: 'No audio recording to upload.' };
  }

  const controller = new AbortController();
  let timeoutId;

  // Combine external signal with timeout
  if (externalSignal) {
    if (externalSignal.aborted) {
      return { ok: false, error: 'Upload was cancelled.' };
    }
    externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  try {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const formData = new FormData();
    // Use the blob's type or fall back to audio/webm
    const ext = audioBlob.type?.includes('ogg') ? 'ogg' : 'webm';
    formData.append('audio', audioBlob, `reference.${ext}`);
    formData.append('userId', userId);

    const url = `${API_BASE_URL}/api/enrol/upload`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const body = await safeParseJson(response);
      const errorMsg = body?.error || body?.message || `Server returned ${response.status}`;
      return {
        ok: false,
        error: errorMsg,
        httpStatus: response.status,
        serverUnavailable: response.status === 404 || response.status === 503,
      };
    }

    const data = await safeParseJson(response);
    if (!data) {
      return { ok: false, error: 'Server returned an invalid response.' };
    }

    return {
      ok: true,
      enrolmentId: data.enrolmentId || data.enrolment_id || data.id,
      status: data.status || 'processing',
    };
  } catch (err) {
    clearTimeout(timeoutId);

    if (err.name === 'AbortError') {
      if (externalSignal?.aborted) {
        return { ok: false, error: 'Upload was cancelled.' };
      }
      return { ok: false, error: `Upload timed out after ${Math.round(timeoutMs / 1000)} seconds.`, networkError: true };
    }

    return {
      ok: false,
      error: `Network error: ${err.message || 'Could not reach the server.'}`,
      networkError: true,
    };
  }
}

/**
 * Poll the enrolment validation status from the backend.
 *
 * @param {string} enrolmentId — The enrolment ID returned by uploadEnrolmentAudio.
 * @param {object} [options]
 * @param {number} [options.timeoutMs] — Request timeout in ms.
 * @param {AbortSignal} [options.signal] — External abort signal.
 * @returns {Promise<{
 *   ok: boolean,
 *   enrolmentId?: string,
 *   status?: 'processing' | 'accepted' | 'rejected',
 *   reason?: string,
 *   error?: string,
 *   httpStatus?: number,
 *   networkError?: boolean,
 * }>}
 */
export async function fetchEnrolmentStatus(enrolmentId, options = {}) {
  const {
    timeoutMs = 10_000,
    signal: externalSignal,
  } = options;

  if (!enrolmentId) {
    return { ok: false, error: 'No enrolment ID provided.' };
  }

  const controller = new AbortController();
  let timeoutId;

  if (externalSignal) {
    if (externalSignal.aborted) {
      return { ok: false, error: 'Status check was cancelled.' };
    }
    externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  try {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const url = `${API_BASE_URL}/api/enrol/status/${encodeURIComponent(enrolmentId)}`;
    const response = await fetch(url, {
      method: 'GET',
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const body = await safeParseJson(response);
      return {
        ok: false,
        error: body?.error || body?.message || `Server returned ${response.status}`,
        httpStatus: response.status,
      };
    }

    const data = await safeParseJson(response);
    if (!data) {
      return { ok: false, error: 'Server returned an invalid status response.' };
    }

    return {
      ok: true,
      enrolmentId: data.enrolmentId || data.enrolment_id || enrolmentId,
      status: data.status,
      reason: data.reason || data.rejection_reason || undefined,
    };
  } catch (err) {
    clearTimeout(timeoutId);

    if (err.name === 'AbortError') {
      if (externalSignal?.aborted) {
        return { ok: false, error: 'Status check was cancelled.' };
      }
      return { ok: false, error: 'Status check timed out.', networkError: true };
    }

    return {
      ok: false,
      error: `Network error: ${err.message || 'Could not reach the server.'}`,
      networkError: true,
    };
  }
}

/**
 * Poll the backend until the enrolment validation is complete or times out.
 *
 * @param {string} enrolmentId
 * @param {object} [options]
 * @param {number} [options.intervalMs] — Polling interval.
 * @param {number} [options.maxAttempts] — Maximum poll attempts.
 * @param {AbortSignal} [options.signal] — External abort signal.
 * @param {(status: object) => void} [options.onPoll] — Called after each poll.
 * @returns {Promise<{
 *   ok: boolean,
 *   status?: string,
 *   reason?: string,
 *   error?: string,
 * }>}
 */
export async function pollUntilComplete(enrolmentId, options = {}) {
  const {
    intervalMs = STATUS_POLL_INTERVAL_MS,
    maxAttempts = MAX_POLL_ATTEMPTS,
    signal,
    onPoll,
  } = options;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (signal?.aborted) {
      return { ok: false, error: 'Polling was cancelled.' };
    }

    const result = await fetchEnrolmentStatus(enrolmentId, { signal });

    if (onPoll) {
      try { onPoll(result); } catch { /* observer error should not break polling */ }
    }

    if (!result.ok) {
      // Network error during polling — retry on next interval
      // unless it's a definitive error (404 = enrolment not found)
      if (result.httpStatus === 404) {
        return { ok: false, error: 'Enrolment not found on the server.' };
      }
      // Continue polling on transient errors
    } else if (result.status === 'accepted' || result.status === 'rejected') {
      return {
        ok: true,
        status: result.status,
        reason: result.reason,
      };
    }
    // status === 'processing': keep polling

    // Wait before next poll
    await delay(intervalMs, signal);
  }

  return { ok: false, error: 'Validation timed out — the server is still processing.' };
}

/* ── Voice verification (Week 4 Tuesday) ─────────────────────────────── */
/*
 * ASSUMED endpoints. They do not exist on the backend yet and are not in
 * docs/contracts.md. Aryan to confirm or change them:
 *
 *   POST /api/enrol/verify/{enrolmentId}/render
 *     Request:  no body.
 *     Response: 200, Content-Type audio/* (e.g. audio/wav), the test
 *               sentence spoken in the cloned voice, as raw audio bytes.
 *
 *   POST /api/enrol/verify/{enrolmentId}/approve
 *     Request:  no body.
 *     Response: 200, JSON { "status": "approved" }.
 *     Anything else (another status, non-2xx, bad JSON) is NOT an approval.
 */

/** Rendering a sentence in a cloned voice may be slow on CPU, so allow longer. */
const VERIFY_RENDER_TIMEOUT_MS = 60_000;

/**
 * Ask the server to render the test sentence in the cloned voice.
 * @param {string} enrolmentId
 * @param {{ signal?: AbortSignal, timeoutMs?: number }} [options]
 * @returns {Promise<{ ok: boolean, audioBlob?: Blob, error?: string,
 *   httpStatus?: number, networkError?: boolean }>}
 */
export async function renderVerificationSample(enrolmentId, options = {}) {
  const url = `${API_BASE_URL}/api/enrol/verify/${encodeURIComponent(enrolmentId)}/render`;
  const result = await postWithTimeout(url, options.signal, options.timeoutMs ?? VERIFY_RENDER_TIMEOUT_MS);
  if (!result.ok) return result;

  // Reading the body can still fail (connection drops, or the caller
  // cancels mid-download), so it is caught like the request itself.
  let audioBlob;
  try {
    audioBlob = await result.response.blob();
  } catch (err) {
    return { ok: false, error: `Could not download the sample: ${err.message}`, networkError: true };
  }
  if (audioBlob.size === 0 || !audioBlob.type.startsWith('audio/')) {
    return { ok: false, error: 'Server did not return an audio sample.' };
  }
  return { ok: true, audioBlob };
}

/**
 * Tell the server the operator approves this voice. Only a 200 with
 * { status: "approved" } counts; the UI shows the voice as active only then.
 * @param {string} enrolmentId
 * @param {{ signal?: AbortSignal, timeoutMs?: number }} [options]
 * @returns {Promise<{ ok: boolean, error?: string, httpStatus?: number, networkError?: boolean }>}
 */
export async function approveVoice(enrolmentId, options = {}) {
  const url = `${API_BASE_URL}/api/enrol/verify/${encodeURIComponent(enrolmentId)}/approve`;
  const result = await postWithTimeout(url, options.signal, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  if (!result.ok) return result;

  const data = await safeParseJson(result.response);
  if (data?.status !== 'approved') {
    return { ok: false, error: 'Server did not confirm the approval.' };
  }
  return { ok: true };
}

/**
 * POST with no body, a timeout and an optional external cancel signal.
 * Both verification calls above need exactly this, so it is shared here.
 * @returns {Promise<{ ok: true, response: Response } | { ok: false, error: string,
 *   httpStatus?: number, networkError?: boolean }>}
 */
async function postWithTimeout(url, externalSignal, timeoutMs) {
  if (externalSignal?.aborted) return { ok: false, error: 'Request was cancelled.' };

  // One controller per request. Aborting it makes fetch() stop the HTTP
  // request and throw an AbortError. Two things can abort it: the timer
  // below, or the caller's signal (e.g. the page was left).
  const controller = new AbortController();
  externalSignal?.addEventListener('abort', () => controller.abort(), { once: true });
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { method: 'POST', signal: controller.signal });
    if (!response.ok) {
      const body = await safeParseJson(response);
      return {
        ok: false,
        error: body?.error || body?.message || `Server returned ${response.status}`,
        httpStatus: response.status,
      };
    }
    return { ok: true, response };
  } catch (err) {
    if (err.name === 'AbortError') {
      if (externalSignal?.aborted) return { ok: false, error: 'Request was cancelled.' };
      return { ok: false, error: `Request timed out after ${Math.round(timeoutMs / 1000)} seconds.`, networkError: true };
    }
    return { ok: false, error: `Network error: ${err.message || 'Could not reach the server.'}`, networkError: true };
  } finally {
    clearTimeout(timeoutId); // runs on every path, so no timer is left behind
  }
}

/* ── Helpers ──────────────────────────────────────────────────────────── */

/**
 * Safely parse a response body as JSON; returns null on failure.
 * @param {Response} response
 * @returns {Promise<object|null>}
 */
async function safeParseJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Promise-based delay that respects an AbortSignal.
 * @param {number} ms
 * @param {AbortSignal} [signal]
 * @returns {Promise<void>}
 */
function delay(ms, signal) {
  return new Promise((resolve) => {
    if (signal?.aborted) { resolve(); return; }
    const id = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => { clearTimeout(id); resolve(); }, { once: true });
  });
}

