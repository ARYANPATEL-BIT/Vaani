/**
 * usePlaybackQueue — schedules incoming PCM audio chunks for gapless playback.
 *
 * Sits between the WebSocket receiver and the speaker:
 *   WebSocket binary frame → enqueue() → AudioContext clock → speaker
 *
 * The only input is raw PCM audio chunks (same format the microphone sends:
 * 16-bit signed little-endian mono at 16 kHz). The hook converts each chunk
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
function pcm16ToAudioBuffer(audioCtx, buffer) {
  const int16 = new Int16Array(buffer);
  const sampleCount = int16.length;

  // One channel (mono), sampleCount frames, at the project's fixed sample rate.
  const audioBuffer = audioCtx.createBuffer(1, sampleCount, AUDIO_SAMPLE_RATE);
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
      audioCtxRef.current = new AudioContextClass({
        sampleRate: AUDIO_SAMPLE_RATE,
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

    const audioBuffer = pcm16ToAudioBuffer(ctx, arrayBuffer);

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

    // Track the source and its gain node for flushing
    const sourceData = { source, gainNode };
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
   * Applies a 10 ms fade-out to avoid clicks.
   */
  const flushPlayback = useCallback(() => {
    if (!audioCtxRef.current) return;
    const ctx = audioCtxRef.current;
    const now = ctx.currentTime;
    const fadeDuration = 0.01; // 10 ms fade-out

    // Stop all tracked sources
    activeSourcesRef.current.forEach(({ source, gainNode }) => {
      try {
        // Apply short fade-out
        gainNode.gain.setValueAtTime(gainNode.gain.value, now);
        gainNode.gain.linearRampToValueAtTime(0, now + fadeDuration);
        
        // Stop after fade
        source.stop(now + fadeDuration);
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

  // Release resources when the component using this hook unmounts.
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  return { enqueue, flushPlayback, cleanup };
}
