/**
 * usePhraseRecorder — hook for capturing short spoken phrases (consent statements,
 * live challenge phrases) during the enrolment flow.
 *
 * Scope (Week 3 Day 4):
 *  - Enforces minimum duration (default 2 s) and maximum auto-stop (default 15 s).
 *  - Tracks elapsed wall-clock seconds via Date.now().
 *  - Live AnalyserNode RMS audio level meter (0–1 amplitude).
 *  - MediaRecorder audio capture with Blob creation and object URL preview.
 *  - Clean resource management: releases mic tracks, AudioContext, RAF loops,
 *    and revokes object URLs on teardown/unmount.
 *
 * States:
 *  'idle' | 'requesting' | 'recording' | 'completed' | 'too_short' | 'failed'
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export const MIN_PHRASE_DURATION_S = 2;
export const MAX_PHRASE_DURATION_S = 15;

export function usePhraseRecorder({
  minDuration = MIN_PHRASE_DURATION_S,
  maxDuration = MAX_PHRASE_DURATION_S,
} = {}) {
  const [recordingState, setRecordingState] = useState('idle');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [level, setLevel] = useState(0); // 0–1 RMS amplitude
  const [errorMessage, setErrorMessage] = useState(null);
  const [recordingBlob, setRecordingBlob] = useState(null);
  const [recordingUrl, setRecordingUrl] = useState(null);

  // Internal refs
  const mediaStreamRef      = useRef(null);
  const audioContextRef     = useRef(null);
  const analyserRef         = useRef(null);
  const mediaRecorderRef    = useRef(null);
  const chunksRef           = useRef([]);
  const startTimeRef        = useRef(null);
  const timerIntervalRef    = useRef(null);
  const levelRafRef         = useRef(null);
  const maxDurationTimerRef = useRef(null);
  const isStoppingRef       = useRef(false);

  // ── Cleanup helpers ──────────────────────────────────────────────────

  const stopLevelMeter = useCallback(() => {
    if (levelRafRef.current !== null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    setLevel(0);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerIntervalRef.current !== null) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }, []);

  const clearMaxDurationTimer = useCallback(() => {
    if (maxDurationTimerRef.current !== null) {
      clearTimeout(maxDurationTimerRef.current);
      maxDurationTimerRef.current = null;
    }
  }, []);

  const releaseStream = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
  }, []);

  const releaseAudioContext = useCallback(() => {
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
      analyserRef.current = null;
    }
  }, []);

  const revokeUrl = useCallback(() => {
    if (recordingUrl) {
      URL.revokeObjectURL(recordingUrl);
    }
  }, [recordingUrl]);

  const teardownSession = useCallback(() => {
    stopLevelMeter();
    stopTimer();
    clearMaxDurationTimer();
    releaseStream();
    releaseAudioContext();
    isStoppingRef.current = false;
  }, [stopLevelMeter, stopTimer, clearMaxDurationTimer, releaseStream, releaseAudioContext]);

  // ── Level meter ──────────────────────────────────────────────────────

  const startLevelMeter = useCallback((analyser) => {
    const bufferLength = analyser.fftSize;
    const dataArray = new Float32Array(bufferLength);

    const tick = () => {
      analyser.getFloatTimeDomainData(dataArray);
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i] * dataArray[i];
      }
      const rms = Math.sqrt(sum / bufferLength);
      setLevel(Math.min(rms * 4, 1));
      levelRafRef.current = requestAnimationFrame(tick);
    };

    levelRafRef.current = requestAnimationFrame(tick);
  }, []);

  // ── Stop recording ───────────────────────────────────────────────────

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

    const elapsed = startTimeRef.current
      ? Math.max(1, Math.round((Date.now() - startTimeRef.current) / 1000))
      : 0;

    mediaRecorderRef.current.onstop = () => {
      const blob = new Blob(chunksRef.current, {
        type: mediaRecorderRef.current.mimeType || 'audio/webm',
      });
      chunksRef.current = [];

      revokeUrl();
      const url = URL.createObjectURL(blob);

      if (elapsed < minDuration) {
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
  }, [
    minDuration,
    stopLevelMeter,
    stopTimer,
    clearMaxDurationTimer,
    revokeUrl,
    releaseStream,
    releaseAudioContext,
  ]);

  // ── Start recording ──────────────────────────────────────────────────

  const startRecording = useCallback(async () => {
    if (recordingState === 'recording' || recordingState === 'requesting') return;

    teardownSession();
    revokeUrl();
    setRecordingBlob(null);
    setRecordingUrl(null);
    setElapsedSeconds(0);
    setErrorMessage(null);
    chunksRef.current = [];

    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMessage(
        'Your browser does not support microphone access (getUserMedia). Try Chrome or Firefox.'
      );
      setRecordingState('failed');
      return;
    }
    if (!window.MediaRecorder) {
      setErrorMessage(
        'Your browser does not support audio recording (MediaRecorder API). Try Chrome or Firefox.'
      );
      setRecordingState('failed');
      return;
    }

    setRecordingState('requesting');

    try {
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

      const mimeType = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/ogg',
        '',
      ].find((m) => m === '' || MediaRecorder.isTypeSupported(m));

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onerror = (e) => {
        console.error('[usePhraseRecorder] MediaRecorder error:', e);
        setErrorMessage('Recording failed unexpectedly. Please try again.');
        setRecordingState('failed');
        teardownSession();
      };

      recorder.start(250);
      startTimeRef.current = Date.now();
      setRecordingState('recording');

      timerIntervalRef.current = setInterval(() => {
        const s = Math.round((Date.now() - startTimeRef.current) / 1000);
        setElapsedSeconds(s);
      }, 500);

      maxDurationTimerRef.current = setTimeout(() => {
        stopRecording();
      }, maxDuration * 1000);
    } catch (err) {
      console.error('[usePhraseRecorder] Failed to start recording:', err);
      teardownSession();

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setErrorMessage(
          'Microphone permission was denied. Please allow microphone access in your browser settings and try again.'
        );
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setErrorMessage('No microphone found. Please connect a microphone and try again.');
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        setErrorMessage(
          'Microphone is in use by another application. Close other apps using the microphone and try again.'
        );
      } else {
        setErrorMessage(err.message || 'Could not access the microphone. Please try again.');
      }
      setRecordingState('failed');
    }
  }, [
    recordingState,
    maxDuration,
    teardownSession,
    revokeUrl,
    startLevelMeter,
    stopRecording,
  ]);

  // ── Re-record / reset ────────────────────────────────────────────────

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

  const reset = useCallback(() => {
    reRecord();
  }, [reRecord]);

  // ── Cleanup on unmount ───────────────────────────────────────────────

  useEffect(() => {
    return () => {
      teardownSession();
      setRecordingUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    recordingState,
    elapsedSeconds,
    level,
    errorMessage,
    recordingBlob,
    recordingUrl,
    startRecording,
    stopRecording,
    reRecord,
    reset,
    minDuration,
    maxDuration,
  };
}
