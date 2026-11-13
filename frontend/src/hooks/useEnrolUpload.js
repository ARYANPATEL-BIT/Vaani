/**
 * useEnrolUpload — React hook for uploading a reference voice recording
 * to the Vaani enrolment API and polling for validation results.
 *
 * Week 4 Day 1: Enrolment API wiring.
 *
 * Responsibilities:
 *  - Submit the recorded audio Blob to POST /api/enrol/upload.
 *  - Show an uploading/processing state to the user.
 *  - Poll GET /api/enrol/status/:enrolmentId until the result is known.
 *  - Return the real validation result (accepted | rejected + reason).
 *  - Handle network errors, timeouts, and malformed responses.
 *  - Prevent duplicate submissions while a request is in-flight.
 *  - Support retry after any failure.
 *  - Support cancelling an in-flight upload/poll.
 *
 * Upload state machine:
 *   idle → uploading → polling → accepted | rejected | error
 *            ↑______________retry___________________________↙
 *
 * The hook does NOT navigate on its own — it hands results back to the
 * caller, which drives navigation. This keeps the hook reusable.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  uploadEnrolmentAudio,
  pollUntilComplete,
  STATUS_POLL_INTERVAL_MS,
  MAX_POLL_ATTEMPTS,
} from '../api/enrolApi.js';

/**
 * Upload states:
 *  'idle'       — nothing in flight, ready to upload.
 *  'uploading'  — POST /api/enrol/upload is in flight.
 *  'polling'    — upload complete, polling GET /api/enrol/status/:id.
 *  'accepted'   — server confirmed the recording is valid.
 *  'rejected'   — server rejected the recording; reason code available.
 *  'error'      — network or server error; retry is available.
 */

export function useEnrolUpload() {
  const [uploadState, setUploadState] = useState('idle');
  const [errorMessage, setErrorMessage] = useState(null);
  const [rejectionReason, setRejectionReason] = useState(null); // raw reason code
  const [enrolmentId, setEnrolmentId]   = useState(null);
  const [pollAttempt, setPollAttempt]   = useState(0);

  // AbortController for the current in-flight operation
  const abortRef = useRef(null);
  // Guard against duplicate submissions
  const inFlightRef = useRef(false);

  // ── Cleanup on unmount ──────────────────────────────────────────────
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // ── Reset to idle ───────────────────────────────────────────────────

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    inFlightRef.current = false;
    setUploadState('idle');
    setErrorMessage(null);
    setRejectionReason(null);
    setEnrolmentId(null);
    setPollAttempt(0);
  }, []);

  // ── Cancel in-flight operation ──────────────────────────────────────

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    inFlightRef.current = false;
    setUploadState('idle');
    setErrorMessage(null);
  }, []);

  // ── Submit upload ───────────────────────────────────────────────────

  /**
   * Upload the audio blob and poll for the validation result.
   *
   * @param {Blob} audioBlob — The recorded reference audio.
   * @param {object} [options]
   * @param {string} [options.userId] — Optional user identifier.
   * @returns {Promise<void>}
   */
  const submit = useCallback(async (audioBlob, options = {}) => {
    // Duplicate-submission guard
    if (inFlightRef.current) {
      return;
    }

    // Validate input
    if (!audioBlob || !(audioBlob instanceof Blob) || audioBlob.size === 0) {
      setErrorMessage('No recording available to upload. Please record your reference voice first.');
      setUploadState('error');
      return;
    }

    // Cancel any prior operation and start fresh
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    inFlightRef.current = true;

    setUploadState('uploading');
    setErrorMessage(null);
    setRejectionReason(null);
    setEnrolmentId(null);
    setPollAttempt(0);

    // ── Step 1: Upload ────────────────────────────────────────────────

    const uploadResult = await uploadEnrolmentAudio(audioBlob, {
      userId: options.userId || 'default',
      signal: controller.signal,
    });

    if (controller.signal.aborted) {
      inFlightRef.current = false;
      return; // cancelled — state already reset by cancel()
    }

    if (!uploadResult.ok) {
      inFlightRef.current = false;
      setErrorMessage(_formatUploadError(uploadResult));
      setUploadState('error');
      return;
    }

    const id = uploadResult.enrolmentId;
    setEnrolmentId(id);

    // If the backend returned an immediate result (no async processing)
    if (uploadResult.status === 'accepted') {
      inFlightRef.current = false;
      setUploadState('accepted');
      return;
    }
    if (uploadResult.status === 'rejected') {
      inFlightRef.current = false;
      setRejectionReason(uploadResult.reason || null);
      setUploadState('rejected');
      return;
    }

    // ── Step 2: Poll for result ───────────────────────────────────────

    setUploadState('polling');

    const pollResult = await pollUntilComplete(id, {
      intervalMs: STATUS_POLL_INTERVAL_MS,
      maxAttempts: MAX_POLL_ATTEMPTS,
      signal: controller.signal,
      onPoll: (result) => {
        // Track polling progress for UI feedback
        setPollAttempt((n) => n + 1);
        // Surface transient poll errors in state without terminating
        if (!result.ok && !controller.signal.aborted) {
          // Just update attempt count; polling will retry
        }
      },
    });

    if (controller.signal.aborted) {
      inFlightRef.current = false;
      return;
    }

    inFlightRef.current = false;

    if (!pollResult.ok) {
      setErrorMessage(pollResult.error || 'Validation check failed. Please try again.');
      setUploadState('error');
      return;
    }

    if (pollResult.status === 'accepted') {
      setUploadState('accepted');
    } else if (pollResult.status === 'rejected') {
      setRejectionReason(pollResult.reason || null);
      setUploadState('rejected');
    } else {
      // Unexpected status
      setErrorMessage(`Unexpected validation status: "${pollResult.status}". Please try again.`);
      setUploadState('error');
    }
  }, []);

  return {
    /** Current state: 'idle' | 'uploading' | 'polling' | 'accepted' | 'rejected' | 'error' */
    uploadState,
    /** Human-readable error message when uploadState === 'error' */
    errorMessage,
    /** Raw rejection reason code when uploadState === 'rejected' (e.g. 'TOO_SHORT') */
    rejectionReason,
    /** Server-assigned enrolment ID (available after upload, for debugging) */
    enrolmentId,
    /** Number of status poll attempts completed (useful for progress display) */
    pollAttempt,
    /** Whether a request is currently in-flight (prevents duplicate submission) */
    isSubmitting: uploadState === 'uploading' || uploadState === 'polling',
    /** Start the upload + poll flow with the given audio Blob */
    submit,
    /** Cancel the current in-flight operation and return to idle */
    cancel,
    /** Reset all state to idle (also cancels in-flight operation) */
    reset,
  };
}

/* ── Helpers ──────────────────────────────────────────────────────────── */

/**
 * Format a structured upload error into a user-facing message string.
 * @param {{ error: string, httpStatus?: number, networkError?: boolean, serverUnavailable?: boolean }} result
 * @returns {string}
 */
function _formatUploadError(result) {
  if (result.serverUnavailable || result.httpStatus === 404) {
    return (
      'The voice enrolment service is not available yet. ' +
      'This feature is scheduled for backend integration. ' +
      'Please check back later.'
    );
  }
  if (result.networkError) {
    return (
      result.error ||
      'Could not reach the server. Please check your connection and try again.'
    );
  }
  if (result.httpStatus === 413) {
    return 'The recording file is too large. Please record a shorter clip (30–60 seconds).';
  }
  if (result.httpStatus === 415) {
    return 'The audio format is not supported by the server. Please try recording again.';
  }
  if (result.httpStatus >= 500) {
    return 'The server encountered an error. Please try again in a moment.';
  }
  return result.error || 'Upload failed. Please try again.';
}

