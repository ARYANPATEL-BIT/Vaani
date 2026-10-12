/**
 * usePlaybackQueue — schedules incoming PCM audio chunks for gapless playback.
 *
 * Sits between the WebSocket receiver and the speaker:
 *   WebSocket binary frame → enqueue() → AudioContext clock → speaker
 *
 * The only input is raw PCM audio chunks (16-bit signed little-endian mono, at
 * the sample_rate the latest audio.start declared). The hook converts each chunk
 * into an AudioBuffer and schedules it onto the Web Audio clock so there is no
 * gap between chunks.
 *
 * Why the audio clock, not setInterval/setTimeout?
 * JavaScript timers are not real-time — they fire when the event loop is free.
 * Under load that can be hundreds of milliseconds late, causing audible gaps.
 * The AudioContext clock (AudioContext.currentTime) runs in the audio hardware
 * thread and advances at a perfectly steady rate regardless of what JavaScript
 * is doing. Scheduling on that clock guarantees gapless output.
 *
 * Day 4 note: flush/interrupt behaviour is implemented via flushPlayback().
 */

import { useRef, useCallback, useEffect } from 'react';
import { AUDIO_SAMPLE_RATE } from '../config.js';

/**
 * Convert a raw ArrayBuffer of Int16LE PCM samples into a Web Audio AudioBuffer.
 *
 * The incoming bytes are 16-bit signed integers, little-endian (matching
 * docs/contracts.md §2.2 and the same format the microphone sends upstream).
 * AudioContext works with Float32 in the range [-1, 1], so we scale by
 * 1/32768 (the maximum Int16 magnitude).
 *
 * @param {AudioContext} audioCtx
 * @param {ArrayBuffer} buffer - raw Int16LE PCM bytes
 * @returns {AudioBuffer}
 */
function pcm16ToAudioBuffer(audioCtx, buffer, sampleRate = AUDIO_SAMPLE_RATE) {
  const int16 = new Int16Array(buffer);
  const sampleCount = int16.length;

  // One channel (mono), sampleCount frames, at the declared sample rate.
  const audioBuffer = audioCtx.createBuffer(1, sampleCount, sampleRate);
  const channelData = audioBuffer.getChannelData(0);

  // Scale Int16 [-32768, 32767] → Float32 [-1.0, 1.0].
  // Dividing by 32768 (not 32767) keeps the mapping symmetric: -32768 → -1.0.
  for (let i = 0; i < sampleCount; i++) {
    channelData[i] = int16[i] / 32768;
  }

  return audioBuffer;
}

export function usePlaybackQueue() {
  // The single AudioContext for playback. Created on first enqueue, destroyed
  // on cleanup. One context for the whole session avoids repeated
  // create/destroy cycles and the browser's autoplay resume requirement.
  const audioCtxRef = useRef(null);

  // The sample rate for incoming audio frames (declared in audio.start, default 16 kHz).
  const currentSampleRateRef = useRef(AUDIO_SAMPLE_RATE);

  // The audio clock time at which the NEXT chunk should start playing.
  // Advances by each chunk's duration after scheduling it.
  // Initialised to 0; reset to 0 on cleanup so a fresh session starts clean.
  const nextStartTimeRef = useRef(0);

  // Set of active AudioBufferSourceNodes to stop on flush.
  const activeSourcesRef = useRef(new Set());

  /**
   * Ensure the AudioContext exists and is running.
   *
   * Browsers suspend audio contexts until a user gesture. Because the user
   * clicks "Start Microphone" before audio arrives, the context is almost
   * certainly already running by the time the first playback chunk lands.
   * We call resume() defensively anyway.
   *
   * @returns {Promise<AudioContext>}
   */
  const getAudioContext = useCallback(async () => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!audioCtxRef.current) {
      // No sampleRate option: the context runs at the output device's own rate
      // (usually 48 kHz). Each AudioBuffer carries the rate audio.start
      // declared, and the browser resamples it up to the device rate. Forcing
      // 16 kHz here would downsample 22050 Hz agent speech and dull it.
      audioCtxRef.current = new AudioContextClass({
        latencyHint: 'interactive',
      });
    }
    const ctx = audioCtxRef.current;
    if (ctx.state === 'suspended') {
      await ctx.resume();
    }
    return ctx;
  }, []);

  /**
   * Accept one raw PCM chunk from the WebSocket and schedule it to play
   * immediately after the previously scheduled chunk.
   *
   * Gapless scheduling rule:
   *   nextStartTime = max(audioCtx.currentTime, nextStartTime)
   *
   * If the queue is empty (or the first chunk), nextStartTime starts at 0
   * which is less than currentTime, so we clamp to currentTime and play
   * immediately. After that each chunk's start time is pushed forward by
   * its duration, giving exactly back-to-back playback with no gaps.
   *
   * @param {ArrayBuffer} arrayBuffer - raw Int16LE PCM bytes from the server
   */
  const enqueue = useCallback(async (arrayBuffer) => {
    let ctx;
    try {
      ctx = await getAudioContext();
    } catch (err) {
      console.error('[usePlaybackQueue] AudioContext failed:', err);
      return;
    }

    const audioBuffer = pcm16ToAudioBuffer(ctx, arrayBuffer, currentSampleRateRef.current);

    // Clamp: if we are behind real time (first chunk, or a gap in server audio),
    // start immediately rather than scheduling in the past (which would be silent).
    const startAt = Math.max(ctx.currentTime, nextStartTimeRef.current);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    
    // Create a GainNode for this source to allow fading out on flush
    const gainNode = ctx.createGain();
    source.connect(gainNode);
    gainNode.connect(ctx.destination);
    
    source.start(startAt);

    // Track the source, its gain node, and scheduled start time for flushing
    const sourceData = { source, gainNode, startAt };
    activeSourcesRef.current.add(sourceData);
    
    // Clean up when the source finishes naturally
    source.onended = () => {
      activeSourcesRef.current.delete(sourceData);
      gainNode.disconnect();
    };

    // Advance the cursor by exactly this chunk's duration.
    nextStartTimeRef.current = startAt + audioBuffer.duration;
  }, [getAudioContext]);

  /**
   * Stop all scheduled playback, clear the queue, and reset scheduling.
   * Applies a 10 ms fade-out to currently playing audio to avoid clicks,
   * silences future-scheduled audio immediately, and resets scheduling cursor to 0.
   */
  const flushPlayback = useCallback(() => {
    if (!audioCtxRef.current) return;
    const ctx = audioCtxRef.current;
    const now = ctx.currentTime;
    const fadeDuration = 0.01; // 10 ms fade-out

    // Stop all tracked sources
    activeSourcesRef.current.forEach(({ source, gainNode, startAt }) => {
      try {
        if (typeof startAt === 'number' && startAt > now) {
          // Chunk was scheduled in the future and has not yet started playing:
          // Silence gain immediately and cancel node without waiting.
          gainNode.gain.setValueAtTime(0, now);
          try {
            source.stop(Math.max(now, startAt));
          } catch {
            source.stop(0);
          }
        } else {
          // Chunk is currently playing:
          // Smoothly ramp gain down to 0 over 10 ms to eliminate pops/clicks.
          gainNode.gain.setValueAtTime(gainNode.gain.value, now);
          gainNode.gain.linearRampToValueAtTime(0, now + fadeDuration);
          source.stop(now + fadeDuration);
        }
      } catch {
        // Ignore if already stopped or invalid state
      }
    });

    // Clear tracked references (onended might not fire predictably after manual stop)
    activeSourcesRef.current.clear();

    // Reset the scheduling cursor so new audio plays immediately
    nextStartTimeRef.current = 0;
  }, []);

  /**
   * Release the AudioContext and reset the scheduling cursor.
   * Called when capture stops or the component unmounts.
   */
  const cleanup = useCallback(() => {
    activeSourcesRef.current.clear();
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    nextStartTimeRef.current = 0;
  }, []);

  /**
   * Update the sample rate for incoming audio frames.
   * Called when an audio.start message arrives with a sample_rate field.
   */
  const setPlaybackSampleRate = useCallback((rate) => {
    if (typeof rate === 'number' && rate > 0) {
      currentSampleRateRef.current = rate;
    }
  }, []);

  // Release resources when the component using this hook unmounts.
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  return { enqueue, flushPlayback, cleanup, setPlaybackSampleRate };
}
