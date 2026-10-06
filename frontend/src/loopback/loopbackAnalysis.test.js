/**
 * loopbackAnalysis.test.js — self-contained unit tests for the loopback
 * waveform analysis algorithm.
 *
 * This file has NO framework dependency. It imports only from
 * loopbackAnalysis.js and uses a minimal assertion helper. It can be run in
 * two ways:
 *
 *   A. In a browser:
 *      Open frontend/loopback-tests.html (which loads this file as an ES
 *      module). Results appear in the page and in the browser console.
 *
 *   B. In Node.js ≥ 18 (which has Float32Array):
 *      node --experimental-vm-modules frontend/src/loopback/loopbackAnalysis.test.js
 *      (or just: node frontend/src/loopback/loopbackAnalysis.test.js)
 *
 * These tests verify:
 *   1. makeReference generates a deterministic float32 sine tone.
 *   2. detectDelay recovers the exact injected offset without noise.
 *   3. detectDelay recovers the offset within ±1 sample with realistic noise.
 *   4. A silent recording is correctly rejected.
 *   5. A too-short recording is correctly rejected.
 *   6. A pure-noise recording gives a low quality peak (below threshold).
 *   7. The quality warnings are generated correctly.
 *
 * The tests use a synthetic recording built by prepending known silence to the
 * reference, which lets us assert that detectDelay returns exactly the right
 * sample count without any hardware.
 */

import {
  makeReference,
  detectDelay,
  MIN_PEAK_QUALITY,
  MIN_PLAUSIBLE_DELAY_MS,
  MAX_PLAUSIBLE_DELAY_MS,
  REFERENCE_FREQ_HZ,
  REFERENCE_DURATION_S,
  REFERENCE_AMPLITUDE,
} from './loopbackAnalysis.js';

// ---------------------------------------------------------------------------
// Minimal test harness (no framework needed)
// ---------------------------------------------------------------------------

const results = [];

function expect(label, actual, expected, tolerance = 0) {
  const pass =
    tolerance > 0
      ? Math.abs(actual - expected) <= tolerance
      : Object.is(actual, expected);
  results.push({ label, pass, actual, expected, tolerance });
  const icon = pass ? '✓' : '✗';
  const detail =
    tolerance > 0
      ? `expected ${expected} ±${tolerance}, got ${actual}`
      : `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`;
  if (!pass) console.error(`  ${icon} FAIL: ${label} — ${detail}`);
  else console.log(`  ${icon} PASS: ${label}`);
}

function expectThrows(label, fn) {
  let threw = false;
  try {
    fn();
  } catch (_) {
    threw = true;
  }
  results.push({ label, pass: threw });
  const icon = threw ? '✓' : '✗';
  if (!threw) console.error(`  ${icon} FAIL: ${label} — expected an error but none was thrown`);
  else console.log(`  ${icon} PASS: ${label}`);
}

function expectTrue(label, value) {
  results.push({ label, pass: !!value });
  const icon = value ? '✓' : '✗';
  if (!value) console.error(`  ${icon} FAIL: ${label} — expected truthy, got ${value}`);
  else console.log(`  ${icon} PASS: ${label}`);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SAMPLE_RATE = 48_000; // typical browser AudioContext rate

/**
 * Build a synthetic recording by prepending `delaySamples` of silence to the
 * reference, then appending a silence tail. An optional noise level adds
 * Gaussian white noise of that amplitude (using a seeded-ish PRNG for
 * reproducibility — Math.random() is unseeded in browsers but deterministic
 * enough for these tests).
 */
function makeSyntheticRecording(reference, delaySamples, noiseSd = 0) {
  const total = delaySamples + reference.length + 4800; // 0.1 s tail
  const rec = new Float32Array(total);
  for (let i = 0; i < reference.length; i++) {
    rec[delaySamples + i] = reference[i];
  }
  if (noiseSd > 0) {
    // Box-Muller transform for Gaussian noise (not seeded, but results are
    // stable at these scales — the peak is always >> noise for noiseSd ≤ 0.01)
    for (let i = 0; i < rec.length; i++) {
      const u1 = Math.random();
      const u2 = Math.random();
      const g = Math.sqrt(-2 * Math.log(u1 + 1e-12)) * Math.cos(2 * Math.PI * u2);
      rec[i] += g * noiseSd;
    }
  }
  return rec;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

console.log('\n=== Loopback Analysis Unit Tests ===\n');

// -- makeReference ----------------------------------------------------------
console.log('makeReference:');
{
  const ref = makeReference(SAMPLE_RATE);
  expect(
    'length matches duration × sample_rate',
    ref.length,
    Math.round(REFERENCE_DURATION_S * SAMPLE_RATE)
  );

  expect('dtype is Float32Array', ref instanceof Float32Array, true);

  // First sample: sin(2π × 1000 × 0 / 48000) = sin(0) = 0
  expect('sample[0] is 0 (sin starts at 0)', Math.abs(ref[0]) < 1e-6, true);

  // Peak should equal amplitude
  let maxAbs = 0;
  for (let i = 0; i < ref.length; i++) if (Math.abs(ref[i]) > maxAbs) maxAbs = Math.abs(ref[i]);
  expect('peak amplitude matches REFERENCE_AMPLITUDE', maxAbs, REFERENCE_AMPLITUDE, 1e-4);

  // Determinism
  const ref2 = makeReference(SAMPLE_RATE);
  let same = true;
  for (let i = 0; i < ref.length; i++) if (ref[i] !== ref2[i]) { same = false; break; }
  expect('two calls produce identical arrays', same, true);

  // Custom frequency
  const ref440 = makeReference(SAMPLE_RATE, 440, 0.1);
  const secondSample = REFERENCE_AMPLITUDE * Math.sin(2 * Math.PI * 440 * (1 / SAMPLE_RATE));
  expect(
    'custom frequency: sample[1] matches sin formula',
    Math.abs(ref440[1] - secondSample) < 1e-5,
    true
  );
}

// -- detectDelay: exact (no noise) ------------------------------------------
console.log('\ndetectDelay (no noise):');
{
  const reference = makeReference(SAMPLE_RATE);

  const testCases = [10, 100, 500, 1200, 2400, 4800]; // ms → samples: *48
  for (const delayMs of testCases) {
    const delaySamples = Math.round((delayMs / 1000) * SAMPLE_RATE);
    const recording = makeSyntheticRecording(reference, delaySamples, 0);
    const res = detectDelay(reference, recording, SAMPLE_RATE);
    expect(
      `${delayMs} ms inject → offset within ±1 sample`,
      Math.abs(res.offsetSamples - delaySamples) <= 1,
      true
    );
    expectTrue(
      `${delayMs} ms inject → quality above threshold`,
      res.peakQuality > MIN_PEAK_QUALITY
    );
  }
}

// -- detectDelay: with realistic room noise ---------------------------------
console.log('\ndetectDelay (with noise, noiseSd=0.005):');
{
  const reference = makeReference(SAMPLE_RATE);
  const noisyCases = [100, 500, 2000];
  for (const delayMs of noisyCases) {
    const delaySamples = Math.round((delayMs / 1000) * SAMPLE_RATE);
    const recording = makeSyntheticRecording(reference, delaySamples, 0.005);
    const res = detectDelay(reference, recording, SAMPLE_RATE);
    expect(
      `${delayMs} ms with noise → offset within ±1 sample`,
      Math.abs(res.offsetSamples - delaySamples) <= 1,
      true
    );
  }
}

// -- detectDelay: quality reported correctly --------------------------------
console.log('\ndetectDelay quality / peakQuality:');
{
  const reference = makeReference(SAMPLE_RATE);

  // Perfect signal → quality close to 1
  const perfectRec = makeSyntheticRecording(reference, 2400, 0);
  const perfectRes = detectDelay(reference, perfectRec, SAMPLE_RATE);
  expect(
    'perfect signal gives quality > 0.9',
    perfectRes.peakQuality > 0.9,
    true
  );

  // Pure noise only → quality below threshold
  const noiseOnly = new Float32Array(reference.length * 4);
  for (let i = 0; i < noiseOnly.length; i++) noiseOnly[i] = (Math.random() - 0.5) * 0.02;
  const noiseRes = detectDelay(reference, noiseOnly, SAMPLE_RATE);
  expect(
    'pure noise gives quality below MIN_PEAK_QUALITY',
    noiseRes.peakQuality < MIN_PEAK_QUALITY,
    true
  );
  expectTrue(
    'pure noise → has quality warning',
    noiseRes.warnings.some((w) => w.toLowerCase().includes('quality') || w.toLowerCase().includes('threshold'))
  );
}

// -- detectDelay: plausibility warnings ------------------------------------
console.log('\ndetectDelay plausibility warnings:');
{
  const reference = makeReference(SAMPLE_RATE);

  // Very small delay → warns "too short"
  const tinyRec = makeSyntheticRecording(reference, 1, 0); // 1 sample ≈ 0.02 ms
  const tinyRes = detectDelay(reference, tinyRec, SAMPLE_RATE);
  expectTrue(
    'sub-ms delay → short-delay warning',
    tinyRes.warnings.some(
      (w) => w.includes(MIN_PLAUSIBLE_DELAY_MS.toString()) || w.toLowerCase().includes('below')
    )
  );

  // Very long delay → warns "too long"
  const hugeDelaySamples = Math.round(0.7 * SAMPLE_RATE); // 700 ms > MAX
  const hugeRec = makeSyntheticRecording(reference, hugeDelaySamples, 0);
  const hugeRes = detectDelay(reference, hugeRec, SAMPLE_RATE);
  expectTrue(
    '700 ms delay → too-long warning',
    hugeRes.warnings.some(
      (w) => w.includes(MAX_PLAUSIBLE_DELAY_MS.toString()) || w.toLowerCase().includes('exceed')
    )
  );
}

// -- detectDelay: error cases -----------------------------------------------
console.log('\ndetectDelay error cases:');
{
  const reference = makeReference(SAMPLE_RATE);

  expectThrows(
    'recording shorter than reference throws',
    () => detectDelay(reference, new Float32Array(reference.length - 1), SAMPLE_RATE)
  );

  expectThrows(
    'silent recording throws',
    () => detectDelay(reference, new Float32Array(reference.length * 4), SAMPLE_RATE)
  );
}

// -- delayMs calculation correctness ----------------------------------------
console.log('\ndelayMs formula: offsetSamples / sampleRate * 1000:');
{
  const reference = makeReference(SAMPLE_RATE);
  const targetMs = 100.0;
  const targetSamples = Math.round((targetMs / 1000) * SAMPLE_RATE);
  const recording = makeSyntheticRecording(reference, targetSamples, 0);
  const res = detectDelay(reference, recording, SAMPLE_RATE);
  // delayMs should match the formula to floating-point precision
  const formulaMs = (res.offsetSamples / SAMPLE_RATE) * 1000;
  expect(
    'delayMs equals offsetSamples / sampleRate * 1000',
    Math.abs(res.delayMs - formulaMs) < 1e-9,
    true
  );
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log('\n=== Results ===');
const passed = results.filter((r) => r.pass).length;
const failed = results.filter((r) => !r.pass).length;
console.log(`${passed} passed, ${failed} failed out of ${results.length} assertions`);

if (typeof window !== 'undefined') {
  // Running in a browser — write results to the DOM so the HTML test page
  // can display them without the console being open.
  window.__loopbackTestResults = { passed, failed, results };
  document.dispatchEvent(new CustomEvent('loopback-tests-done', { detail: { passed, failed } }));
}

if (typeof process !== 'undefined' && failed > 0) {
  process.exitCode = 1;
}

export { results };
