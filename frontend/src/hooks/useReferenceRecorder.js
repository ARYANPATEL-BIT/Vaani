/**
 * useReferenceRecorder — hook for reference-voice recording during enrolment.
 *
 * Manages the full lifecycle of a browser-side reference recording:
 *   - Microphone permission request
 *   - MediaRecorder capture (Opus/WebM or whatever the browser prefers)
 *   - Elapsed-time tracking (real wall-clock via Date.now())
 *   - Live RMS level meter via AnalyserNode (real audio measurements)
 *   - 30-second minimum / 60-second automatic stop enforcement
 *   - Re-recording (releases prior resources before starting fresh)
 *   - Resource cleanup on unmount and after each session
 *
 * Recording state machine:
 *   idle → recording → completed | too_short | failed
 *           ↑__re-record_________↙
 *
 * The captured Blob is held in memory only; nothing is uploaded.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export const MIN_DURATION_S = 30;
export const MAX_DURATION_S = 60;

/**
 * Recording states:
 *  'idle'       — ready to start, no recording exists.
 *  'requesting' — getUserMedia is in flight.
 *  'recording'  — actively recording.
 *  'completed'  — recording stopped and is >= MIN_DURATION_S.
 *  'too_short'  — recording stopped before MIN_DURATION_S.
 *  'failed'     — an unrecoverable error occurred.
 */

export function useReferenceRecorder() {
  const [recordingState, setRecordingState] = useState('idle');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [level, setLevel] = useState(0);           // 0–1 RMS amplitude
  const [errorMessage, setErrorMessage] = useState(null);
  const [recordingBlob, setRecordingBlob] = useState(null);
  const [recordingUrl, setRecordingUrl] = useState(null);

  // Internal refs — avoids stale closure issues
  const mediaStreamRef      = useRef(null);
  const audioContextRef     = useRef(null);
  const analyserRef         = useRef(null);
  const mediaRecorderRef    = useRef(null);
  const chunksRef           = useRef([]);
  const startTimeRef        = useRef(null);
  const timerIntervalRef    = useRef(null);
  const levelRafRef         = useRef(null);
  const maxDurationTimerRef = useRef(null);
  const isStoppingRef       = useRef(false); // prevent double-stop

  // ── cleanup helpers ──────────────────────────────────────────────────

  /** Release analyser RAF loop. */
  const stopLevelMeter = useCallback(() => {
    if (levelRafRef.current !== null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    setLevel(0);
  }, []);

  /** Release the elapsed-time interval. */
  const stopTimer = useCallback(() => {
    if (timerIntervalRef.current !== null) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }, []);

  /** Clear the 60-second auto-stop timer. */
  const clearMaxDurationTimer = useCallback(() => {
    if (maxDurationTimerRef.current !== null) {
      clearTimeout(maxDurationTimerRef.current);
      maxDurationTimerRef.current = null;
    }
  }, []);

  /** Stop and release the microphone stream. */
  const releaseStream = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(t => t.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  /** Close the AudioContext (best-effort). */
  const releaseAudioContext = useCallback(() => {
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
      analyserRef.current = null;
    }
  }, []);

  /** Revoke any previously-created object URL. */
  const revokeUrl = useCallback(() => {
    if (recordingUrl) {
      URL.revokeObjectURL(recordingUrl);
    }
  }, [recordingUrl]);

  /**
   * Full teardown — call this whenever a recording session ends (success,
   * failure, or re-record). Does NOT touch recordingBlob / recordingUrl;
   * those are kept for the caller to read after completion.
   */
  const teardownSession = useCallback(() => {
    stopLevelMeter();
    stopTimer();
    clearMaxDurationTimer();
    releaseStream();
    releaseAudioContext();
    isStoppingRef.current = false;
  }, [stopLevelMeter, stopTimer, clearMaxDurationTimer, releaseStream, releaseAudioContext]);

  // ── level meter ──────────────────────────────────────────────────────

  /** Start the RAF loop that reads from the AnalyserNode and updates level. */
  const startLevelMeter = useCallback((analyser) => {
    const bufferLength = analyser.fftSize;
    const dataArray = new Float32Array(bufferLength);

    const tick = () => {
      analyser.getFloatTimeDomainData(dataArray);
      // RMS of the audio samples
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i] * dataArray[i];
      }
      const rms = Math.sqrt(sum / bufferLength);
      // Normalise to roughly 0–1 (microphone typically peaks around 0.5 RMS
      // at loud speech; clamp above 1 to be safe).
      setLevel(Math.min(rms * 4, 1));
      levelRafRef.current = requestAnimationFrame(tick);
    };

    levelRafRef.current = requestAnimationFrame(tick);
  }, []);

  // ── stop recording ───────────────────────────────────────────────────

  /**
   * Finalise the current recording session.
   * Called either by the user (Stop button) or automatically at 60 seconds.
   */
  const stopRecording = useCallback(() => {
    if (isStoppingRef.current) return;
    if (!mediaRecorderRef.current) return;
    if (
      mediaRecorderRef.current.state !== 'recording' &&
      mediaRecorderRef.current.state !== 'paused'
    ) return;

    isStoppingRef.current = true;
    stopLevelMeter();
    stopTimer();
    clearMaxDurationTimer();

    // Calculate elapsed before stopping (onstop fires asynchronously)
    const elapsed = startTimeRef.current
      ? Math.round((Date.now() - startTimeRef.current) / 1000)
      : 0;

    // onstop fires after stop() resolves the pending chunks
    mediaRecorderRef.current.onstop = () => {
      const blob = new Blob(chunksRef.current, {
        type: mediaRecorderRef.current.mimeType || 'audio/webm',
      });
      chunksRef.current = [];

      revokeUrl(); // revoke any prior URL
      const url = URL.createObjectURL(blob);

      if (elapsed < MIN_DURATION_S) {
        setRecordingBlob(null);
        setRecordingUrl(null);
        setRecordingState('too_short');
      } else {
        setRecordingBlob(blob);
        setRecordingUrl(url);
        setRecordingState('completed');
      }

      releaseStream();
      releaseAudioContext();
      isStoppingRef.current = false;
    };

    mediaRecorderRef.current.stop();
  }, [stopLevelMeter, stopTimer, clearMaxDurationTimer, revokeUrl, releaseStream, releaseAudioContext]);

  // ── start recording ──────────────────────────────────────────────────

  const startRecording = useCallback(async () => {
    // Guard: only start from idle, too_short, or completed states.
    if (recordingState === 'recording' || recordingState === 'requesting') return;

    // Clean up any prior session resources.
    teardownSession();
    revokeUrl();
    setRecordingBlob(null);
    setRecordingUrl(null);
    setElapsedSeconds(0);
    setErrorMessage(null);
    chunksRef.current = [];

    // Check browser support before requesting permissions.
    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMessage('Your browser does not support microphone access (getUserMedia). Try a modern browser like Chrome or Firefox.');
      setRecordingState('failed');
      return;
    }
    if (!window.MediaRecorder) {
      setErrorMessage('Your browser does not support audio recording (MediaRecorder API). Try a modern browser like Chrome or Firefox.');
      setRecordingState('failed');
      return;
    }

    setRecordingState('requesting');

    try {
      // Step 1: request microphone permission.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      mediaStreamRef.current = stream;

      // Step 2: build AnalyserNode for live level meter.
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      if (AudioCtxClass) {
        const ctx = new AudioCtxClass();
        audioContextRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.6;
        source.connect(analyser);
        analyserRef.current = analyser;
        startLevelMeter(analyser);
      }

      // Step 3: choose a supported MIME type.
      const mimeType = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
        '',
      ].find(m => m === '' || MediaRecorder.isTypeSupported(m));

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = e => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onerror = (e) => {
        console.error('[useReferenceRecorder] MediaRecorder error:', e);
        setErrorMessage('Recording failed unexpectedly. Please try again.');
        setRecordingState('failed');
        teardownSession();
      };

      // Step 4: start recording, collect in 250ms chunks.
      recorder.start(250);
      startTimeRef.current = Date.now();
      setRecordingState('recording');

      // Step 5: elapsed timer (tick every second from wall clock).
      timerIntervalRef.current = setInterval(() => {
        const s = Math.round((Date.now() - startTimeRef.current) / 1000);
        setElapsedSeconds(s);
      }, 500); // 500ms ticks keep display accurate

      // Step 6: auto-stop at MAX_DURATION_S.
      maxDurationTimerRef.current = setTimeout(() => {
        stopRecording();
      }, MAX_DURATION_S * 1000);

    } catch (err) {
      console.error('[useReferenceRecorder] Failed to start recording:', err);
      teardownSession();

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setErrorMessage(
          'Microphone permission was denied. Please allow microphone access in your browser settings and try again.'
        );
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setErrorMessage(
          'No microphone found. Please connect a microphone and try again.'
        );
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        setErrorMessage(
          'Microphone is in use by another application. Close other apps using the microphone and try again.'
        );
      } else {
        setErrorMessage(err.message || 'Could not access the microphone. Please try again.');
      }
      setRecordingState('failed');
    }
  }, [recordingState, teardownSession, revokeUrl, startLevelMeter, stopRecording]);

  // ── re-record ────────────────────────────────────────────────────────

  /** Discard current recording and return to idle so the user can retry. */
  const reRecord = useCallback(() => {
    teardownSession();
    revokeUrl();
    setRecordingBlob(null);
    setRecordingUrl(null);
    setElapsedSeconds(0);
    setErrorMessage(null);
    setLevel(0);
    setRecordingState('idle');
  }, [teardownSession, revokeUrl]);

  // ── cleanup on unmount ───────────────────────────────────────────────

  useEffect(() => {
    return () => {
      teardownSession();
      // Revoke any held object URL.
      setRecordingUrl(prev => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    recordingState,   // 'idle' | 'requesting' | 'recording' | 'completed' | 'too_short' | 'failed'
    elapsedSeconds,   // integer, seconds elapsed during recording
    level,            // 0–1 RMS amplitude for the level meter
    errorMessage,
    recordingBlob,    // Blob | null — in-memory only, never uploaded
    recordingUrl,     // object URL for <audio> preview | null
    startRecording,
    stopRecording: () => stopRecording('user'),
    reRecord,
  };
}
