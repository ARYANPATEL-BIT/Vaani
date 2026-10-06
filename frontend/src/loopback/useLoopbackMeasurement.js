/**
 * useLoopbackMeasurement — React hook that orchestrates the loopback rig.
 *
 * Workflow (in order):
 *
 *  1. Generate a deterministic sine-tone reference at the AudioContext's
 *     native sample rate.
 *  2. Request microphone permission via getUserMedia.
 *  3. Create a MediaStreamDestination node to hold the microphone input.
 *  4. Create a ScriptProcessorNode (deprecated but universally available)
 *     or AnalyserNode to accumulate raw microphone samples.
 *  5. Create an AudioBufferSourceNode loaded with the reference and play it
 *     on the AudioContext's destination (the speakers).
 *  6. While the reference is playing, capture the microphone into a
 *     Float32Array accumulator.
 *  7. Once the capture window elapses, stop recording and pass both signals
 *     to detectDelay() from loopbackAnalysis.js.
 *  8. Store and expose the result.
 *
 * The delay is NOT measured from JavaScript timestamps. It comes entirely
 * from the sample offset returned by detectDelay().
 *
 * Design decisions:
 * - AudioContext runs at the native device rate (e.g. 44100 or 48000 Hz),
 *   NOT at 16 kHz. The loopback rig is independent of the voice pipeline.
 *   makeReference() takes sampleRate as an argument so it always matches.
 * - getUserMedia is called with echoCancellation: false. Echo cancellation
 *   would suppress exactly the reference signal we are trying to capture.
 * - The hook is completely isolated from useAudioCapture and usePlaybackQueue
 *   so it cannot interfere with a live voice session.
 */

import { useState, useRef, useCallback } from 'react';
import {
  makeReference,
  detectDelay,
  SILENCE_TAIL_S,
  RECORD_DURATION_S,
} from './loopbackAnalysis.js';

/**
 * @typedef {object} MeasurementResult
 * @property {number} offsetSamples
 * @property {number} delayMs
 * @property {number} peakQuality
 * @property {string[]} warnings
 * @property {number} sampleRate
 * @property {string} inputLabel
 */

/**
 * @typedef {'idle'|'requesting'|'recording'|'analysing'|'done'|'error'} RigStatus
 */

export function useLoopbackMeasurement() {
  /** @type {[RigStatus, Function]} */
  const [status, setStatus] = useState('idle');
  /** @type {[MeasurementResult|null, Function]} */
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // Audio resources — held in refs so they are accessible in async callbacks
  // without triggering re-renders.
  const audioCtxRef = useRef(null);
  const streamRef = useRef(null);
  const accumulatorRef = useRef(/** @type {Float32Array[]} */ ([]));

  /**
   * Release all audio resources created during a measurement.
   *
   * Called after a measurement completes (success or failure) and also when
   * the component unmounts.
   */
  const teardown = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    accumulatorRef.current = [];
  }, []);

  /**
   * Run one full loopback measurement.
   *
   * Creates a fresh AudioContext each time so there is no state left over
   * from a previous run (or from the voice pipeline's AudioContext).
   *
   * @returns {Promise<void>}
   */
  const measure = useCallback(async () => {
    // Prevent concurrent measurements
    if (status === 'recording' || status === 'analysing') return;

    setResult(null);
    setErrorMessage(null);
    setStatus('requesting');
    accumulatorRef.current = [];

    // -----------------------------------------------------------------------
    // Step 1: Browser / API availability checks
    // -----------------------------------------------------------------------
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      setErrorMessage('Web Audio API (AudioContext) is not supported in this browser.');
      setStatus('error');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMessage('Microphone access (getUserMedia) is not supported in this browser.');
      setStatus('error');
      return;
    }

    try {
      // -----------------------------------------------------------------------
      // Step 2: Request microphone permission.
      //
      // CRITICAL: echoCancellation and noiseSuppression must be OFF.
      // AEC tries to remove from the recording any sound that was just played
      // through the speaker — which is exactly the reference signal we need
      // to capture. Leaving AEC on would delete the evidence.
      // -----------------------------------------------------------------------
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: false, // must be off — see comment above
            noiseSuppression: false, // we want the raw room acoustic
            autoGainControl: false,  // fixed gain for reproducible measurements
          },
          video: false,
        });
      } catch (permErr) {
        if (permErr.name === 'NotAllowedError' || permErr.name === 'PermissionDeniedError') {
          setErrorMessage(
            'Microphone permission denied. Allow microphone access in your browser and try again.'
          );
        } else {
          setErrorMessage(`Microphone unavailable: ${permErr.message}`);
        }
        setStatus('error');
        return;
      }
      streamRef.current = stream;

      // -----------------------------------------------------------------------
      // Step 3: Create AudioContext at the device's native rate.
      //
      // We do NOT force 16000 Hz here. The loopback rig is independent of the
      // voice pipeline. We generate the reference at whatever rate the device
      // supports (typically 44100 or 48000 Hz), correlate in that space, and
      // then convert the offset to ms.
      // -----------------------------------------------------------------------
      const ctx = new AudioContextClass({ latencyHint: 'interactive' });
      audioCtxRef.current = ctx;
      if (ctx.state === 'suspended') await ctx.resume();

      const sampleRate = ctx.sampleRate;
      const recordSamples = Math.round(RECORD_DURATION_S * sampleRate);

      // -----------------------------------------------------------------------
      // Step 4: Build the capture graph.
      //
      // mic → MediaStreamSource → ScriptProcessor → (accumulate samples)
      //                                            → destination (muted)
      //
      // ScriptProcessorNode is deprecated in favour of AudioWorklet, but:
      // - AudioWorklet requires a separately served .js file, which would need
      //   a new public/ file and a fresh addModule() call.
      // - ScriptProcessorNode is universally supported in all current browsers.
      // - The rig runs for < 2 s and is not on the production audio path, so
      //   the main-thread callback latency is acceptable.
      //
      // bufferSize=4096 gives us 4096-sample chunks at whatever rate the device
      // runs. We accumulate until we have enough samples.
      // -----------------------------------------------------------------------
      const bufferSize = 4096;
      // ScriptProcessorNode is on the AudioContext prototype
      const scriptProcessor = ctx.createScriptProcessor(bufferSize, 1, 1);
      const micSource = ctx.createMediaStreamSource(stream);

      // Mute the output of the script processor so we do not feed the mic
      // back to the speakers (which would create an echo loop).
      const muteGain = ctx.createGain();
      muteGain.gain.value = 0;

      micSource.connect(scriptProcessor);
      scriptProcessor.connect(muteGain);
      muteGain.connect(ctx.destination);

      // Accumulate incoming Float32 samples
      scriptProcessor.onaudioprocess = (event) => {
        const channelData = event.inputBuffer.getChannelData(0);
        accumulatorRef.current.push(new Float32Array(channelData));
      };

      // -----------------------------------------------------------------------
      // Step 5: Generate the reference at the device sample rate and play it.
      //
      // makeReference() uses the same formula every time, so the waveform is
      // identical across runs at the same sample rate.
      // -----------------------------------------------------------------------
      setStatus('recording');

      const reference = makeReference(sampleRate);
      const silenceTailSamples = Math.round(SILENCE_TAIL_S * sampleRate);

      // Build an AudioBuffer long enough for the tone + silence tail
      const playbackBuffer = ctx.createBuffer(
        1,
        reference.length + silenceTailSamples,
        sampleRate
      );
      playbackBuffer.getChannelData(0).set(reference); // samples 0..R-1 are the tone
      // samples R..end are already zero (silence)

      const source = ctx.createBufferSource();
      source.buffer = playbackBuffer;
      source.connect(ctx.destination);
      source.start();

      // -----------------------------------------------------------------------
      // Step 6: Wait for the full capture window to elapse.
      //
      // We use a timer here, but it is ONLY used to know when to stop
      // recording — not to measure the delay. The delay comes from the
      // waveform offset in Step 7.
      // -----------------------------------------------------------------------
      await new Promise((resolve) =>
        setTimeout(resolve, RECORD_DURATION_S * 1000)
      );

      // Disconnect microphone to stop accumulating
      micSource.disconnect();
      scriptProcessor.disconnect();
      muteGain.disconnect();

      // -----------------------------------------------------------------------
      // Step 7: Flatten the accumulated chunks into one recording array.
      // -----------------------------------------------------------------------
      setStatus('analysing');

      const totalSamples = accumulatorRef.current.reduce(
        (acc, chunk) => acc + chunk.length,
        0
      );

      if (totalSamples === 0) {
        throw new Error(
          'No audio was captured from the microphone. ' +
            'The microphone may be muted or reporting all-zero samples.'
        );
      }

      const recording = new Float32Array(totalSamples);
      let offset = 0;
      for (const chunk of accumulatorRef.current) {
        recording.set(chunk, offset);
        offset += chunk.length;
      }

      // Trim to the expected window length if we over-captured.
      const trimmed =
        recording.length > recordSamples
          ? recording.subarray(0, recordSamples)
          : recording;

      // -----------------------------------------------------------------------
      // Step 8: Run the waveform analysis.
      //
      // detectDelay() returns the sample offset at which the reference appears
      // in the recording. This is the ONLY source of the delay number.
      // -----------------------------------------------------------------------
      const delayResult = detectDelay(reference, trimmed, sampleRate);

      // Resolve the input device label from the MediaStream track
      const tracks = stream.getAudioTracks();
      const inputLabel = tracks.length > 0
        ? (tracks[0].label || 'Microphone (unknown label)')
        : 'Microphone';

      setResult({
        ...delayResult,
        sampleRate,
        inputLabel,
      });
      setStatus('done');

    } catch (err) {
      console.error('[useLoopbackMeasurement]', err);
      setErrorMessage(err.message || 'Measurement failed. See console for details.');
      setStatus('error');
    } finally {
      teardown();
    }
  }, [status, teardown]);

  /**
   * Reset to idle so the user can run another measurement.
   */
  const reset = useCallback(() => {
    teardown();
    setStatus('idle');
    setResult(null);
    setErrorMessage(null);
  }, [teardown]);

  return {
    status,
    result,
    errorMessage,
    measure,
    reset,
  };
}
