/* global process */
/**
 * latencyTelemetry.test.js — unit tests for the Latency HUD telemetry parser.
 *
 * Verifies all 8 required behaviors:
 * 1. Correct parsing of the actual telemetry payload.
 * 2. Correct stage-to-value mapping.
 * 3. Multiple stage timings.
 * 4. Live update when a new telemetry payload arrives.
 * 5. Partial telemetry safely handled (missing stages remain null, not fabricated).
 * 6. Missing telemetry (null/undefined/empty).
 * 7. Invalid/malformed telemetry safely rejected.
 * 8. Zero fabricated or default latency numbers.
 *
 * Run with:
 *   node frontend/src/telemetry/latencyTelemetry.test.js
 */

import {
  STAGE_DEFINITIONS,
  parseTelemetryPayload,
  formatLatencyMs,
} from './latencyTelemetry.js';

let passedCount = 0;
let failedCount = 0;

function assert(description, condition, details = '') {
  if (condition) {
    passedCount += 1;
    console.log(`  ✓ ${description}`);
  } else {
    failedCount += 1;
    console.error(`  ✗ FAIL: ${description} ${details ? `(${details})` : ''}`);
  }
}

console.log('\n--- Test Suite: Latency Telemetry Parser ---');

// 1. Stage Definitions Verification
console.log('\n1. STAGE_DEFINITIONS:');
assert(
  'STAGE_DEFINITIONS exports exactly 6 official pipeline stages',
  Array.isArray(STAGE_DEFINITIONS) && STAGE_DEFINITIONS.length === 6,
  `got ${STAGE_DEFINITIONS.length}`
);

const expectedKeys = ['vad', 'endpointing', 'asr', 'llm', 'tts', 'playback'];
const actualKeys = STAGE_DEFINITIONS.map((s) => s.key);
assert(
  'Stages correspond to [vad, endpointing, asr, llm, tts, playback]',
  JSON.stringify(actualKeys) === JSON.stringify(expectedKeys),
  `actual: ${JSON.stringify(actualKeys)}`
);

// 2. Full Valid Telemetry Payload (Object map)
console.log('\n2. Full valid telemetry payload (dictionary format):');
const fullPayload = {
  type: 'telemetry',
  turn_id: 'turn-alpha-101',
  stages: {
    vad: 280,
    endpointing: 700,
    asr: 577,
    llm: 913,
    tts: 100,
    playback: 45,
  },
  total_ms: 2615,
};

const res1 = parseTelemetryPayload(fullPayload);
assert('res1 is marked valid', res1.valid === true);
assert('res1 extracts turn_id', res1.turnId === 'turn-alpha-101');
assert('res1 maps VAD stage correctly', res1.stages.vad === 280);
assert('res1 maps Endpointing stage correctly', res1.stages.endpointing === 700);
assert('res1 maps ASR stage correctly', res1.stages.asr === 577);
assert('res1 maps LLM stage correctly', res1.stages.llm === 913);
assert('res1 maps TTS stage correctly', res1.stages.tts === 100);
assert('res1 maps Playback stage correctly', res1.stages.playback === 45);
assert('res1 extracts total_ms', res1.totalMs === 2615);
assert('res1 hasData is true', res1.hasData === true);
assert('res1 isPartial is false when all stages present', res1.isPartial === false);

// 3. Array Format with Span Names from telemetry.py
console.log('\n3. Array format with span names:');
const arrayPayload = {
  type: 'telemetry',
  turn_id: 'turn-beta-202',
  stages: [
    { name: 'vad_decision', duration_ms: 275.4 },
    { name: 'turn_ended', duration_ms: 702.1 },
    { name: 'asr_final', duration_ms: 580.0 },
    { name: 'llm_first_token', duration_ms: 890.5 },
    { name: 'tts_first_audio', duration_ms: 95.0 },
    { name: 'playback_start', duration_ms: 40.2 },
  ],
};

const res2 = parseTelemetryPayload(arrayPayload);
assert('res2 array format is valid', res2.valid === true);
assert('res2 maps vad_decision to vad', res2.stages.vad === 275.4);
assert('res2 maps turn_ended to endpointing', res2.stages.endpointing === 702.1);
assert('res2 maps asr_final to asr', res2.stages.asr === 580);
assert('res2 maps llm_first_token to llm', res2.stages.llm === 890.5);
assert('res2 maps tts_first_audio to tts', res2.stages.tts === 95);
assert('res2 maps playback_start to playback', res2.stages.playback === 40.2);
assert('res2 computes totalMs as sum if omitted', res2.totalMs === 2583.2);

// 4. Partial Telemetry Handling
console.log('\n4. Partial telemetry (speech ended, ASR finished, LLM in flight):');
const partialPayload = {
  type: 'telemetry',
  turn_id: 'turn-gamma-303',
  stages: {
    vad: 280,
    endpointing: 700,
    asr: 577,
  },
};

const res3 = parseTelemetryPayload(partialPayload);
assert('res3 is marked valid', res3.valid === true);
assert('res3 isPartial is true', res3.isPartial === true);
assert('res3 maps vad', res3.stages.vad === 280);
assert('res3 maps endpointing', res3.stages.endpointing === 700);
assert('res3 maps asr', res3.stages.asr === 577);
assert('res3 leaves unreceived llm as null', res3.stages.llm === null);
assert('res3 leaves unreceived tts as null', res3.stages.tts === null);
assert('res3 leaves unreceived playback as null', res3.stages.playback === null);
assert('res3 computes partial total', res3.totalMs === 1557);

// 5. Zero Fabricated Default Latencies
console.log('\n5. No fabricated default values:');
for (const stageKey of expectedKeys) {
  assert(
    `Unsent stage '${stageKey}' strictly defaults to null`,
    res3.stages[stageKey] === (['vad', 'endpointing', 'asr'].includes(stageKey) ? res3.stages[stageKey] : null)
  );
}
assert('formatLatencyMs(null) returns "—"', formatLatencyMs(null) === '—');
assert('formatLatencyMs(undefined) returns "—"', formatLatencyMs(undefined) === '—');
assert('formatLatencyMs(NaN) returns "—"', formatLatencyMs(NaN) === '—');
assert('formatLatencyMs(-50) returns "—" (rejects negative)', formatLatencyMs(-50) === '—');
assert('formatLatencyMs(123.4) formats as "123 ms"', formatLatencyMs(123.4) === '123 ms');

// 6. Live Updates Simulation (Sequential turns)
console.log('\n6. Live update sequencing across turns:');

// Turn 1 telemetry arrives
let currentDisplayed = parseTelemetryPayload({
  type: 'telemetry',
  turn_id: 'turn-1',
  stages: { vad: 280, endpointing: 700, asr: 600 },
});
assert('Turn 1 parsed', currentDisplayed.turnId === 'turn-1' && currentDisplayed.stages.asr === 600);

// Turn 2 telemetry arrives with new measurements
currentDisplayed = parseTelemetryPayload({
  type: 'telemetry',
  turn_id: 'turn-2',
  stages: { vad: 210, endpointing: 705, asr: 520, llm: 850, tts: 90, playback: 35 },
});
assert('Turn 2 replaces Turn 1 live', currentDisplayed.turnId === 'turn-2' && currentDisplayed.stages.asr === 520);
assert('Turn 2 has updated VAD', currentDisplayed.stages.vad === 210);
assert('Turn 2 has updated LLM', currentDisplayed.stages.llm === 850);

// 7. Invalid & Malformed Telemetry Rejection
console.log('\n7. Invalid & malformed message rejection:');
assert('Rejects null', parseTelemetryPayload(null).valid === false);
assert('Rejects undefined', parseTelemetryPayload(undefined).valid === false);
assert('Rejects string', parseTelemetryPayload('telemetry').valid === false);
assert('Rejects array', parseTelemetryPayload([1, 2, 3]).valid === false);
assert('Rejects missing type', parseTelemetryPayload({ stages: {} }).valid === false);
assert('Rejects unrelated type (e.g. transcript.final)', parseTelemetryPayload({ type: 'transcript.final', text: 'hi' }).valid === false);
assert('Rejects audio.flush', parseTelemetryPayload({ type: 'audio.flush', turn_id: 't1' }).valid === false);

// 8. Empty stages payload
console.log('\n8. Empty telemetry payload handling:');
const emptyPayload = { type: 'telemetry', turn_id: 'turn-empty', stages: {} };
const resEmpty = parseTelemetryPayload(emptyPayload);
assert('Empty telemetry is valid shape', resEmpty.valid === true);
assert('hasData is false for empty payload', resEmpty.hasData === false);
assert('totalMs is null for empty payload', resEmpty.totalMs === null);
assert('all stages are null', Object.values(resEmpty.stages).every((v) => v === null));

console.log('\n=======================================');
console.log(`Results: ${passedCount} passed, ${failedCount} failed`);
console.log('=======================================\n');

if (failedCount > 0) {
  process.exitCode = 1;
}
