/**
 * loopbackAnalysis.js — pure signal-processing functions for the loopback rig.
 *
 * No React, no DOM, no AudioContext. Everything here takes plain Float32Arrays
 * and returns plain numbers so the logic can be tested without a browser.
 *
 * The single public entrypoint is detectDelay(), which runs cross-correlation
 * between a known reference waveform and a microphone recording, and returns
 * the sample offset at which the reference appears in the recording.
 *
 * All delay measurement is derived from that offset:
 *
 *   round_trip_delay_ms = offset_samples / sample_rate * 1000
 *
 * Application timestamps, console.log times, and JS scheduler timing are
 * never used to derive the reported delay.
 */

// ---------------------------------------------------------------------------
// Reference signal
// ---------------------------------------------------------------------------

/**
 * Configuration for the loopback reference signal.
 *
 * These constants are read by both the analysis functions (which use
 * REFERENCE_FREQ_HZ to generate the reference) and the React hook (which
 * uses RECORD_DURATION_S to size the recording capture window).
 */
export const REFERENCE_FREQ_HZ = 1000; // 1 kHz sine tone — audible and correlated well
export const REFERENCE_DURATION_S = 0.5; // half a second is long enough to correlate against
export const SILENCE_TAIL_S = 0.5; // silence after the tone so the recording captures the tail
export const RECORD_DURATION_S = REFERENCE_DURATION_S + SILENCE_TAIL_S + 0.5; // total window
export const REFERENCE_AMPLITUDE = 0.7; // fraction of full scale; loud but below clipping

// Quality thresholds
export const MIN_PEAK_QUALITY = 0.35; // normalised correlation peak below this → weak signal
export const MIN_PLAUSIBLE_DELAY_MS = 1.0; // sub-ms results are almost certainly digital loopback
export const MAX_PLAUSIBLE_DELAY_MS = 600.0; // beyond 600 ms the coupling is not a direct path

/**
 * Generate a deterministic sine-tone reference signal as a Float32Array.
 *
 * The same arguments always produce the same waveform, making the reference
 * reproducible across measurement runs.
 *
 * @param {number} sampleRate - AudioContext sample rate in Hz (e.g. 48000).
 * @param {number} [freqHz=REFERENCE_FREQ_HZ] - Tone frequency.
 * @param {number} [durationS=REFERENCE_DURATION_S] - Duration in seconds.
 * @param {number} [amplitude=REFERENCE_AMPLITUDE] - Peak amplitude in [0, 1].
 * @returns {Float32Array}
 */
export function makeReference(
  sampleRate,
  freqHz = REFERENCE_FREQ_HZ,
  durationS = REFERENCE_DURATION_S,
  amplitude = REFERENCE_AMPLITUDE,
) {
  const n = Math.round(durationS * sampleRate);
  const ref = new Float32Array(n);
  const twoPiF = 2 * Math.PI * freqHz;
  for (let i = 0; i < n; i++) {
    // sin is in [-1, 1]; scale by amplitude
    ref[i] = amplitude * Math.sin(twoPiF * (i / sampleRate));
  }
  return ref;
}

// ---------------------------------------------------------------------------
// Cross-correlation delay detection
// ---------------------------------------------------------------------------

/**
 * Normalise a Float32Array to zero mean and unit standard deviation.
 *
 * Both the reference and the recording are normalised before correlation so
 * that the peak value is independent of gain differences between the speaker
 * and microphone devices.
 *
 * Throws if the signal is silent (all zeros or near-zero RMS), because
 * correlating silence against a tone produces meaningless results.
 *
 * @param {Float32Array} x
 * @returns {Float32Array}
 * @throws {Error} if RMS < 1e-9
 */
function normalise(x) {
  let sum = 0;
  for (let i = 0; i < x.length; i++) sum += x[i];
  const mean = sum / x.length;

  let variance = 0;
  for (let i = 0; i < x.length; i++) {
    const d = x[i] - mean;
    variance += d * d;
  }
  const std = Math.sqrt(variance / x.length);

  if (std < 1e-9) {
    throw new Error(
      'Signal is silent (RMS ≈ 0). Check microphone or reference signal.'
    );
  }

  const out = new Float32Array(x.length);
  for (let i = 0; i < x.length; i++) {
    out[i] = (x[i] - mean) / std;
  }
  return out;
}

/**
 * Cross-correlate `recording` against `reference` for causal lags only.
 *
 * "Causal" means we only look at positions where the reference could appear
 * after the recording started (lag ≥ 0). A negative lag would mean the
 * microphone captured the sound before it was played — physically impossible.
 *
 * The naive O(n·m) implementation is fine for the short signals used here
 * (≤ 1.5 s × 48 000 Hz = 72 000 samples): correlation completes in < 5 ms
 * in a modern browser. If signals grow longer, an FFT-based approach should
 * be substituted.
 *
 * @param {Float32Array} refN - Normalised reference (length R).
 * @param {Float32Array} recN - Normalised recording (length ≥ R).
 * @returns {{ peakLag: number, peakValue: number, maxPossible: number }}
 */
function crossCorrelate(refN, recN) {
  const R = refN.length;
  const N = recN.length;
  // Maximum lag we can compute: the reference must fit inside the recording.
  const maxLag = N - R;

  let peakLag = 0;
  let peakValue = -Infinity;

  for (let lag = 0; lag <= maxLag; lag++) {
    let dot = 0;
    for (let i = 0; i < R; i++) {
      dot += refN[i] * recN[lag + i];
    }
    if (dot > peakValue) {
      peakValue = dot;
      peakLag = lag;
    }
  }

  // The theoretical maximum: correlating the reference with itself gives
  // the sum of its squared values (since it is normalised, this ≈ R).
  let maxPossible = 0;
  for (let i = 0; i < R; i++) maxPossible += refN[i] * refN[i];

  return { peakLag, peakValue, maxPossible };
}

/**
 * @typedef {object} DelayResult
 * @property {number} offsetSamples - Detected lag in samples.
 * @property {number} delayMs - Converted round-trip delay in milliseconds.
 * @property {number} peakQuality - Normalised correlation quality in [0, 1].
 * @property {string[]} warnings - Non-fatal quality warnings.
 */

/**
 * Detect the round-trip delay from a reference and a microphone recording.
 *
 * This is the only function that derives the delay number reported to the
 * user. The formula is:
 *
 *   delay_ms = offsetSamples / sampleRate * 1000
 *
 * No application timestamps are read here.
 *
 * @param {Float32Array} reference - The known reference waveform.
 * @param {Float32Array} recording - The raw microphone capture.
 * @param {number} sampleRate - Sample rate of both signals in Hz.
 * @returns {DelayResult}
 * @throws {Error} if the recording is too short, or if either signal is silent.
 */
export function detectDelay(reference, recording, sampleRate) {
  if (recording.length < reference.length) {
    throw new Error(
      `Recording (${recording.length} samples) is shorter than the reference ` +
        `(${reference.length} samples). Increase the capture window.`
    );
  }

  // Normalise both signals before correlating.
  // This throws if either is silent, surfacing the problem early.
  const refN = normalise(reference);
  const recN = normalise(recording);

  const { peakLag, peakValue, maxPossible } = crossCorrelate(refN, recN);

  // Normalised quality: 1.0 = perfect match, 0 = no match.
  const peakQuality = maxPossible > 0 ? peakValue / maxPossible : 0;

  const delayMs = (peakLag / sampleRate) * 1000;
  const warnings = [];

  if (peakQuality < MIN_PEAK_QUALITY) {
    warnings.push(
      `Correlation quality ${peakQuality.toFixed(3)} is below threshold ` +
        `${MIN_PEAK_QUALITY}. The reference signal may not have been captured. ` +
        `Check your hardware connection (speaker → microphone).`
    );
  }
  if (delayMs < MIN_PLAUSIBLE_DELAY_MS) {
    warnings.push(
      `Delay ${delayMs.toFixed(2)} ms is below ${MIN_PLAUSIBLE_DELAY_MS} ms. ` +
        `Possible digital loopback — the measurement may not reflect the real audio path.`
    );
  }
  if (delayMs > MAX_PLAUSIBLE_DELAY_MS) {
    warnings.push(
      `Delay ${delayMs.toFixed(2)} ms exceeds ${MAX_PLAUSIBLE_DELAY_MS} ms. ` +
        `The reference may not have been detected correctly.`
    );
  }

  return { offsetSamples: peakLag, delayMs, peakQuality, warnings };
}
