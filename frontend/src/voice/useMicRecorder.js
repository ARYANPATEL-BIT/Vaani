/**
 * useMicRecorder -- record one take from the microphone, as a Blob.
 *
 * The browser's three voice-call filters are switched OFF (MIC_CONSTRAINTS):
 *   autoGainControl   turns the volume up in pauses, so room noise swells
 *                     between words; it wrecked the voice-cloning spike's
 *                     recordings (clip A read about 5 dB SNR);
 *   noiseSuppression  removes noise by also removing parts of the voice;
 *   echoCancellation  subtracts what it thinks is speaker echo.
 * All three help a video call and hurt a cloning reference: the model copies
 * whatever it hears, so it should hear the raw voice.
 *
 * MediaRecorder encodes the take (WebM with Opus in Chrome); the studio's
 * decoder (PyAV) reads that directly. Recording stops by itself at
 * `maxSeconds`, so a forgotten take cannot grow past the server's limit.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export const MIC_CONSTRAINTS = {
  audio: {
    channelCount: 1,
    autoGainControl: false,
    noiseSuppression: false,
    echoCancellation: false,
  },
  video: false,
};

export function useMicRecorder(maxSeconds) {
  const [state, setState] = useState('idle'); // idle | recording | done | error
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState(null);
  const [error, setError] = useState(null);
  const recorderRef = useRef(null);
  const timerRef = useRef(null);

  const stop = useCallback(() => {
    clearInterval(timerRef.current);
    // stop() makes MediaRecorder hand over the last data, then fire 'stop'.
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setBlob(null);
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
    } catch (err) {
      setError(`The microphone could not be opened (${err.name}).`);
      setState('error');
      return;
    }
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop()); // the mic light goes off
      setBlob(new Blob(chunks, { type: recorder.mimeType }));
      setState('done');
    };
    recorderRef.current = recorder;
    recorder.start();
    const startedAt = performance.now();
    setSeconds(0);
    setState('recording');
    timerRef.current = setInterval(() => {
      const elapsed = (performance.now() - startedAt) / 1000;
      setSeconds(elapsed);
      if (elapsed >= maxSeconds) stop();
    }, 200);
  }, [maxSeconds, stop]);

  const reset = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder?.state === 'recording') {
      // Discard this take: its 'stop' event arrives later and must not
      // bring the blob back after the reset below.
      recorder.onstop = () => recorder.stream.getTracks().forEach((t) => t.stop());
    }
    stop();
    setBlob(null);
    setSeconds(0);
    setState('idle');
  }, [stop]);

  // Leaving the page mid-take releases the microphone.
  useEffect(() => stop, [stop]);

  return { state, seconds, blob, error, start, stop, reset };
}
