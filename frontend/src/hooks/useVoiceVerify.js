/**
 * useVoiceVerify — runs the voice verification screen (/enrol/verify).
 *
 * It connects three things to the state machine in enrol/verifyState.js:
 *   1. the network: render the test sentence, then approve the voice
 *      (api/enrolApi.js, or enrol/verifyDemo.js in demo mode);
 *   2. cancellation: one AbortController per request, aborted when the
 *      user leaves the page, so no request outlives the screen;
 *   3. the <audio> element that plays the sample (the page renders it and
 *      attaches audioRef; this hook starts, stops and listens to it).
 */

import { useCallback, useEffect, useReducer, useRef } from 'react';
import { renderVerificationSample, approveVoice } from '../api/enrolApi.js';
import { demoRender, demoApprove } from '../enrol/verifyDemo.js';
import { verifyReducer, initialVerifyState, canApprove } from '../enrol/verifyState.js';

const NO_ENROLMENT_ERROR = 'There is no enrolment to verify. Record your reference voice first.';

/**
 * @param {string|null} enrolmentId — from the validation page's router state.
 * @param {string|null} demoMode — 'ok' | 'load-error' | 'approve-error', or null for the real server.
 */
export function useVoiceVerify(enrolmentId, demoMode) {
  const hasTarget = Boolean(enrolmentId || demoMode);

  // Without an enrolment there is nothing to load, so start in 'error'.
  const [state, dispatch] = useReducer(verifyReducer, null, () =>
    hasTarget ? initialVerifyState : { ...initialVerifyState, status: 'error', error: NO_ENROLMENT_ERROR },
  );

  const audioRef = useRef(null);
  const sampleUrlRef = useRef(null);   // the object URL, so it can be freed on unmount
  const approveAbortRef = useRef(null);

  // ── Load the sample whenever we enter 'loading' (first mount, or retry) ──
  const isLoading = state.status === 'loading';
  useEffect(() => {
    if (!isLoading || !hasTarget) return undefined;

    // AbortController: an object with one method, abort(), and one property,
    // signal. We pass the signal to fetch(); calling abort() makes fetch stop
    // the HTTP request and give up. The cleanup function below calls it, so
    // leaving the page mid-render cancels the request instead of letting it
    // finish and update a screen that no longer exists.
    const controller = new AbortController();

    (async () => {
      const result = demoMode
        ? await demoRender(demoMode, { signal: controller.signal })
        : await renderVerificationSample(enrolmentId, { signal: controller.signal });

      if (controller.signal.aborted) return; // page left or effect re-ran: ignore the answer

      if (!result.ok) {
        dispatch({ type: 'LOAD_FAIL', error: describeError(result, 'load the test sentence') });
        return;
      }
      // An object URL is a short "blob:..." address that points at bytes held
      // in browser memory. <audio src> can play it like any URL. It must be
      // freed with URL.revokeObjectURL, or the bytes stay in memory.
      const url = URL.createObjectURL(result.audioBlob);
      sampleUrlRef.current = url;
      dispatch({ type: 'LOAD_OK', sampleUrl: url });
    })();

    return () => controller.abort();
  }, [isLoading, hasTarget, enrolmentId, demoMode]);

  // ── On unmount: cancel an approval in flight, free the sample's memory ──
  useEffect(() => () => {
    approveAbortRef.current?.abort();
    if (sampleUrlRef.current) URL.revokeObjectURL(sampleUrlRef.current);
  }, []);

  // ── Playback ──────────────────────────────────────────────────────────
  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (state.status === 'playing') {
      audio.pause();
      audio.currentTime = 0; // next play starts from the beginning
      dispatch({ type: 'STOPPED' });
      return;
    }
    if (state.status !== 'ready') return;
    dispatch({ type: 'PLAY' });
    // play() returns a promise that rejects if the browser refuses to play.
    audio.play().catch((err) => {
      dispatch({ type: 'PLAY_FAIL', error: `The browser could not play the sample (${err.name}).` });
    });
  }, [state.status]);

  const onEnded = useCallback(() => dispatch({ type: 'ENDED' }), []);
  const onAudioError = useCallback(() => {
    dispatch({ type: 'PLAY_FAIL', error: 'The browser could not decode the sample.' });
  }, []);

  // ── Approve: the voice becomes active only on the server's "approved" ──
  const approve = useCallback(async () => {
    if (!canApprove(state)) return; // also blocks a double click: we are in 'approving'
    dispatch({ type: 'APPROVE' });

    const controller = new AbortController();
    approveAbortRef.current = controller;
    const result = demoMode
      ? await demoApprove(demoMode, { signal: controller.signal })
      : await approveVoice(enrolmentId, { signal: controller.signal });

    if (controller.signal.aborted) return;
    dispatch(result.ok
      ? { type: 'APPROVE_OK' }
      : { type: 'APPROVE_FAIL', error: describeError(result, 'approve the voice') });
  }, [state, demoMode, enrolmentId]);

  const retryLoad = useCallback(() => dispatch({ type: 'RETRY_LOAD' }), []);

  return { state, hasTarget, audioRef, togglePlay, onEnded, onAudioError, approve, retryLoad };
}

/** Turn an API result into one sentence the user can act on. */
function describeError(result, action) {
  if (result.httpStatus === 404 || result.httpStatus === 503) {
    return `Could not ${action}: the voice verification service is not available on the server yet.`;
  }
  if (result.networkError) {
    return `Could not ${action} (${result.error}). Check that the backend is running.`;
  }
  return `Could not ${action}: ${result.error}`;
}
