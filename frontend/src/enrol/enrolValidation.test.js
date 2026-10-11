/* global process */
/**
 * enrolValidation.test.js — Contract and unit tests for enrolment validation feedback.
 *
 * Verifies Week 3 Day 5 requirements:
 * 1. Every supported rejection reason displays its own specific, distinct message.
 * 2. Aliases for backend domain codes (e.g. VOICE_TOO_SHORT, VOICE_TOO_QUIET) normalize correctly.
 * 3. Specific remedy guidance is provided for each rejection reason.
 * 4. Resilient handling of malformed and unknown payloads (does not crash or hide errors).
 * 5. Action pathways ('rerecord' vs 'consent') match reason requirements.
 * 6. Client pre-validation enforces DATA-2 duration (30-60s) and signal checks.
 *
 * Run with:
 *   node frontend/src/enrol/enrolValidation.test.js
 */

import {
  REJECTION_REASONS,
  REJECTION_FEEDBACK_DETAILS,
  parseValidationFeedback,
  clientPreValidateRecording,
} from './enrolValidationContracts.js';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed++;
    console.log(`  ✓ ${description}`);
  } else {
    failed++;
    console.error(`  ✗ FAIL: ${description}`);
  }
}

console.log('=== Enrolment Validation Feedback Contract Tests ===\n');

// 1. Every supported reason code has a unique, specific message and details
console.log('1. Supported reason codes completeness and uniqueness:');

const supportedCodes = [
  REJECTION_REASONS.TOO_SHORT,
  REJECTION_REASONS.TOO_LONG,
  REJECTION_REASONS.TOO_QUIET,
  REJECTION_REASONS.CLIPPING,
  REJECTION_REASONS.EXCESSIVE_SILENCE,
  REJECTION_REASONS.INSUFFICIENT_SPEECH,
  REJECTION_REASONS.LOW_SNR,
  REJECTION_REASONS.UNSUPPORTED_FORMAT,
  REJECTION_REASONS.CONSENT_MISSING,
  REJECTION_REASONS.CHALLENGE_MISMATCH,
  REJECTION_REASONS.UNKNOWN,
];

const titles = new Set();
const messages = new Set();
const remedies = new Set();

supportedCodes.forEach((code) => {
  const detail = REJECTION_FEEDBACK_DETAILS[code];
  assert(`Code '${code}' exists in specifications`, Boolean(detail));
  assert(`Code '${code}' has non-empty title`, Boolean(detail.title && detail.title.trim()));
  assert(`Code '${code}' has non-empty specific message`, Boolean(detail.message && detail.message.trim()));
  assert(`Code '${code}' has non-empty actionable remedy`, Boolean(detail.remedy && detail.remedy.trim()));
  assert(`Code '${code}' has valid category`, Boolean(detail.category));

  titles.add(detail.title);
  messages.add(detail.message);
  remedies.add(detail.remedy);
});

assert(
  'Every supported reason has a distinct title',
  titles.size === supportedCodes.length
);
assert(
  'Every supported reason has a distinct specific message',
  messages.size === supportedCodes.length
);
assert(
  'Every supported reason has a distinct remedy',
  remedies.size === supportedCodes.length
);

// 2. Normalization of string codes and aliases
console.log('\n2. Reason code alias normalization:');

const aliasTests = [
  { raw: 'TOO_SHORT', expected: REJECTION_REASONS.TOO_SHORT },
  { raw: 'voice_too_short', expected: REJECTION_REASONS.TOO_SHORT },
  { raw: 'DURATION_TOO_SHORT', expected: REJECTION_REASONS.TOO_SHORT },
  { raw: 'TOO_LONG', expected: REJECTION_REASONS.TOO_LONG },
  { raw: 'VOICE_TOO_LONG', expected: REJECTION_REASONS.TOO_LONG },
  { raw: 'TOO_QUIET', expected: REJECTION_REASONS.TOO_QUIET },
  { raw: 'voice_too_quiet', expected: REJECTION_REASONS.TOO_QUIET },
  { raw: 'LOW_VOLUME', expected: REJECTION_REASONS.TOO_QUIET },
  { raw: 'CLIPPING', expected: REJECTION_REASONS.CLIPPING },
  { raw: 'voice_clipping', expected: REJECTION_REASONS.CLIPPING },
  { raw: 'AUDIO_CLIPPING', expected: REJECTION_REASONS.CLIPPING },
  { raw: 'EXCESSIVE_SILENCE', expected: REJECTION_REASONS.EXCESSIVE_SILENCE },
  { raw: 'LONG_SILENCE', expected: REJECTION_REASONS.EXCESSIVE_SILENCE },
  { raw: 'INSUFFICIENT_SPEECH', expected: REJECTION_REASONS.INSUFFICIENT_SPEECH },
  { raw: 'NO_SPEECH_DETECTED', expected: REJECTION_REASONS.INSUFFICIENT_SPEECH },
  { raw: 'LOW_SNR', expected: REJECTION_REASONS.LOW_SNR },
  { raw: 'NOISY_BACKGROUND', expected: REJECTION_REASONS.LOW_SNR },
  { raw: 'UNSUPPORTED_FORMAT', expected: REJECTION_REASONS.UNSUPPORTED_FORMAT },
  { raw: 'CONSENT_MISSING', expected: REJECTION_REASONS.CONSENT_MISSING },
  { raw: 'VOICE_CONSENT_MISSING', expected: REJECTION_REASONS.CONSENT_MISSING },
  { raw: 'CHALLENGE_MISMATCH', expected: REJECTION_REASONS.CHALLENGE_MISMATCH },
  { raw: 'VOICE_CHALLENGE_MISMATCH', expected: REJECTION_REASONS.CHALLENGE_MISMATCH },
];

aliasTests.forEach(({ raw, expected }) => {
  const parsed = parseValidationFeedback(raw);
  assert(`Alias '${raw}' maps to canonical '${expected}'`, parsed.canonicalCode === expected);
  assert(`Parsed '${raw}' has isKnownReason === true`, parsed.isKnownReason === true);
});

// 3. Payload structures handling (API errors, direct objects, WebSocket errors)
console.log('\n3. Diverse payload structure parsing:');

// RFC 7807 / standard error object
const apiErrorPayload = {
  error: {
    code: 'VOICE_TOO_QUIET',
    message: 'Recorded amplitude was 0.01 RMS (below 0.03 floor).',
  },
};
const parsedApi = parseValidationFeedback(apiErrorPayload);
assert('API error object maps to TOO_QUIET', parsedApi.canonicalCode === REJECTION_REASONS.TOO_QUIET);
assert('API error preserves backend serverMessage', parsedApi.serverMessage.includes('Recorded amplitude was 0.01'));

// Direct validation object
const directRejectionPayload = {
  valid: false,
  reason: 'CLIPPING',
  message: 'Multiple samples clipped the maximum 16-bit threshold.',
};
const parsedDirect = parseValidationFeedback(directRejectionPayload);
assert('Direct object maps to CLIPPING', parsedDirect.canonicalCode === REJECTION_REASONS.CLIPPING);
assert('Direct object preserves serverMessage', parsedDirect.serverMessage.includes('Multiple samples clipped'));

// WebSocket error payload
const wsErrorPayload = {
  type: 'error',
  code: 'VOICE_TOO_SHORT',
  message: 'Audio duration 18.2s is below 30s threshold.',
};
const parsedWs = parseValidationFeedback(wsErrorPayload);
assert('WS error object maps to TOO_SHORT', parsedWs.canonicalCode === REJECTION_REASONS.TOO_SHORT);

// 4. Unknown and malformed inputs do not throw and preserve codes
console.log('\n4. Resilient handling of malformed and unknown inputs:');

assert('Handles null safely', parseValidationFeedback(null).canonicalCode === REJECTION_REASONS.UNKNOWN);
assert('Handles undefined safely', parseValidationFeedback(undefined).canonicalCode === REJECTION_REASONS.UNKNOWN);
assert('Handles empty object safely', parseValidationFeedback({}).canonicalCode === REJECTION_REASONS.UNKNOWN);
assert('Handles empty string safely', parseValidationFeedback('').canonicalCode === REJECTION_REASONS.UNKNOWN);

const unknownCodePayload = { code: 'ALIEN_INTERFERENCE_DETECTED' };
const parsedUnknown = parseValidationFeedback(unknownCodePayload);
assert('Unknown code maps to UNKNOWN canonical reason', parsedUnknown.canonicalCode === REJECTION_REASONS.UNKNOWN);
assert('Unknown code preserves raw code', parsedUnknown.rawCode === 'ALIEN_INTERFERENCE_DETECTED');
assert('Unknown code sets isKnownReason to false', parsedUnknown.isKnownReason === false);

// 5. Recovery action routing
console.log('\n5. Recovery action routing:');

assert(
  'TOO_SHORT routes to rerecord action',
  parseValidationFeedback(REJECTION_REASONS.TOO_SHORT).action === 'rerecord'
);
assert(
  'TOO_QUIET routes to rerecord action',
  parseValidationFeedback(REJECTION_REASONS.TOO_QUIET).action === 'rerecord'
);
assert(
  'CONSENT_MISSING routes to consent action',
  parseValidationFeedback(REJECTION_REASONS.CONSENT_MISSING).action === 'consent'
);
assert(
  'CHALLENGE_MISMATCH routes to consent action',
  parseValidationFeedback(REJECTION_REASONS.CHALLENGE_MISMATCH).action === 'consent'
);

// 6. Client pre-validation checks
console.log('\n6. Client-side pre-validation:');

assert(
  'Rejects unconfirmed consent with CONSENT_MISSING',
  clientPreValidateRecording({ durationSeconds: 45, isConsentConfirmed: false }).error.canonicalCode ===
    REJECTION_REASONS.CONSENT_MISSING
);

assert(
  'Rejects duration under 30s with TOO_SHORT',
  clientPreValidateRecording({ durationSeconds: 25, isConsentConfirmed: true }).error.canonicalCode ===
    REJECTION_REASONS.TOO_SHORT
);

assert(
  'Rejects duration over 60s with TOO_LONG',
  clientPreValidateRecording({ durationSeconds: 65, isConsentConfirmed: true }).error.canonicalCode ===
    REJECTION_REASONS.TOO_LONG
);

assert(
  'Rejects very quiet audio with TOO_QUIET',
  clientPreValidateRecording({ durationSeconds: 40, avgLevel: 0.01, isConsentConfirmed: true }).error.canonicalCode ===
    REJECTION_REASONS.TOO_QUIET
);

assert(
  'Passes valid 45s recording with normal level',
  clientPreValidateRecording({ durationSeconds: 45, avgLevel: 0.45, isConsentConfirmed: true }).valid === true
);

console.log(`\n─── Results: ${passed} passed, ${failed} failed ───`);

if (failed > 0) {
  process.exit(1);
}
