/* global AudioWorkletProcessor, registerProcessor */

/**
 * Vaani AudioWorkletProcessor — captures microphone audio and emits 20 ms frames.
 *
 * Runs on the dedicated audio rendering thread (off the main UI thread).
 * Receives Web Audio render quanta (typically 128 samples per process call)
 * at 16 kHz mono, accumulates them into 20 ms frames (320 samples = 640 bytes),
 * converts Float32 [-1.0, 1.0] to signed 16-bit linear PCM (Int16LE), and
 * transfers the binary ArrayBuffer to the main thread via postMessage.
 *
 * Push-to-talk stop (docs/contracts.md §2.8): the main thread posts 'flush'.
 * The processor then sends the samples it is still holding as one last frame,
 * padded with silence to the full 640 bytes the server requires, followed by
 * a { type: 'last-frame' } marker. Messages on a port arrive in the order they
 * were posted, so when the marker arrives every frame of the press has
 * already reached the main thread (src/ptt/pttPress.js).
 */

const FRAME_SAMPLES = 320; // 16 000 Hz * 0.020 s = 320 samples (20 ms)

class VaaniAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // Accumulation buffer sized to hold up to 2 frames of incoming audio
    this.buffer = new Float32Array(FRAME_SAMPLES * 2);
    this.bufferedCount = 0;
    // Runs on the audio thread between render quanta, never during process().
    this.port.onmessage = (event) => {
      if (event.data === 'flush') {
        this.flushLastFrame();
      }
    };
  }

  /**
   * Convert the first `count` buffered samples to one Int16 frame and post it.
   * A frame is always FRAME_SAMPLES long; samples past `count` stay 0 (silence).
   */
  postFrame(count) {
    const pcm16 = new Int16Array(FRAME_SAMPLES);

    for (let i = 0; i < count; i++) {
      // Clamp sample to [-1.0, 1.0] range
      const s = Math.max(-1, Math.min(1, this.buffer[i]));
      // Quantize Float32 to Int16 [-32768, 32767]
      pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    // Transfer the underlying ArrayBuffer (zero-copy transfer)
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
  }

  /** Push-to-talk stop: the partial frame (if any), then the marker. */
  flushLastFrame() {
    if (this.bufferedCount > 0) {
      this.postFrame(this.bufferedCount);
      this.bufferedCount = 0;
    }
    this.port.postMessage({ type: 'last-frame' });
  }

  /**
   * Called by the audio rendering engine for each audio quantum (128 samples).
   *
   * @param {Float32Array[][]} inputs - Array of inputs, each with channel arrays
   * @param {Float32Array[][]} outputs - Array of outputs
   * @param {Record<string, Float32Array>} parameters - Parameter values
   * @returns {boolean} true to keep processor alive
   */
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) {
      return true;
    }

    const channelData = input[0];
    const incomingLength = channelData.length;

    // Append incoming samples to our accumulation buffer
    for (let i = 0; i < incomingLength; i++) {
      this.buffer[this.bufferedCount + i] = channelData[i];
    }
    this.bufferedCount += incomingLength;

    // Whenever we have at least one complete 20 ms frame (320 samples),
    // convert and dispatch it to the main thread.
    while (this.bufferedCount >= FRAME_SAMPLES) {
      this.postFrame(FRAME_SAMPLES);

      // Shift remaining samples to the front of the accumulator
      const remaining = this.bufferedCount - FRAME_SAMPLES;
      for (let i = 0; i < remaining; i++) {
        this.buffer[i] = this.buffer[FRAME_SAMPLES + i];
      }
      this.bufferedCount = remaining;
    }

    return true;
  }
}

registerProcessor('vaani-audio-processor', VaaniAudioProcessor);
