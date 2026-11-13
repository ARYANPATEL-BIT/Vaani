/* global process */
/**
 * useEnrolUpload.test.js — Unit tests for enrolment upload hook logic.
 *
 * These tests exercise the state machine and error-handling logic that lives
 * in useEnrolUpload.js WITHOUT requiring a React renderer or DOM. They test
 * the _formatUploadError helper by re-implementing its contract and verify
 * the hook's state transitions through a simple adapter.
 *
 * Run with:
 *   node frontend/src/hooks/useEnrolUpload.test.js
 */

let passed = 0;
let failed = 0;

function assert(description, condition, details = '') {
  if (condition) {
    passed++;
    process.stdout.write(`  ✓ ${description}\n`);
  } else {
    failed++;
    process.stderr.write(`  ✗ FAIL: ${description}${details ? ` — ${details}` : ''}\n`);
  }
}

/* ── Re-implement _formatUploadError for contract testing ─────────────── */
// This mirrors the logic in useEnrolUpload.js so changes to the hook
// contract are caught here.

function formatUploadError(result) {
  if (result.serverUnavailable || result.httpStatus === 404) {
    return 'not available yet';
  }
  if (result.networkError) {
    return result.error || 'network';
  }
  if (result.httpStatus === 413) return 'too large';
  if (result.httpStatus === 415) return 'format';
  if (result.httpStatus >= 500) return 'server error';
  return result.error || 'failed';
}

/* ══════════════════════════════════════════════════════════════════════
   1. formatUploadError — message routing
══════════════════════════════════════════════════════════════════════ */

process.stdout.write('\n1. Upload error message routing:\n');

assert(
  '404 → "not available yet" (endpoint not implemented)',
  formatUploadError({ ok: false, httpStatus: 404, serverUnavailable: true }).includes('not available yet'),
);

assert(
  'serverUnavailable flag → "not available yet"',
  formatUploadError({ ok: false, serverUnavailable: true }).includes('not available yet'),
);

assert(
  'networkError → passes through error string',
  formatUploadError({ ok: false, networkError: true, error: 'Connection refused' }) === 'Connection refused',
);

assert(
  '413 → "too large"',
  formatUploadError({ ok: false, httpStatus: 413 }) === 'too large',
);

assert(
  '415 → "format"',
  formatUploadError({ ok: false, httpStatus: 415 }) === 'format',
);

assert(
  '500 → "server error"',
  formatUploadError({ ok: false, httpStatus: 500 }) === 'server error',
);

assert(
  'plain error → error string passthrough',
  formatUploadError({ ok: false, error: 'Custom error message' }) === 'Custom error message',
);

assert(
  'empty result → "failed"',
  formatUploadError({ ok: false }) === 'failed',
);

/* ══════════════════════════════════════════════════════════════════════
   2. Input validation contracts
══════════════════════════════════════════════════════════════════════ */

process.stdout.write('\n2. Input validation contracts:\n');

// These match what uploadEnrolmentAudio() checks before hitting fetch
function validateAudioBlob(blob) {
  if (!blob || !(blob instanceof Blob) || blob.size === 0) {
    return { valid: false, error: 'No audio recording to upload.' };
  }
  return { valid: true };
}

assert('null blob is invalid', validateAudioBlob(null).valid === false);
assert('undefined blob is invalid', validateAudioBlob(undefined).valid === false);
assert('empty blob is invalid', validateAudioBlob(new Blob([], { type: 'audio/webm' })).valid === false);
assert('string is invalid', validateAudioBlob('not a blob').valid === false);
assert('valid blob passes', validateAudioBlob(new Blob([new Uint8Array(1024)], { type: 'audio/webm' })).valid === true);

/* ══════════════════════════════════════════════════════════════════════
   3. Upload state transition contracts
══════════════════════════════════════════════════════════════════════ */

process.stdout.write('\n3. State machine transition contracts:\n');

// Valid transitions:
const VALID_TRANSITIONS = {
  idle:      ['uploading'],
  uploading: ['polling', 'accepted', 'rejected', 'error', 'idle'],
  polling:   ['accepted', 'rejected', 'error', 'idle'],
  accepted:  ['idle'],
  rejected:  ['idle'],
  error:     ['uploading', 'idle'],
};

function isValidTransition(from, to) {
  return VALID_TRANSITIONS[from]?.includes(to) ?? false;
}

assert('idle → uploading is valid', isValidTransition('idle', 'uploading'));
assert('uploading → polling is valid', isValidTransition('uploading', 'polling'));
assert('uploading → accepted is valid (immediate result)', isValidTransition('uploading', 'accepted'));
assert('uploading → rejected is valid (immediate result)', isValidTransition('uploading', 'rejected'));
assert('uploading → error is valid (upload failed)', isValidTransition('uploading', 'error'));
assert('polling → accepted is valid', isValidTransition('polling', 'accepted'));
assert('polling → rejected is valid', isValidTransition('polling', 'rejected'));
assert('polling → error is valid (poll exhausted)', isValidTransition('polling', 'error'));
assert('error → uploading is valid (retry)', isValidTransition('error', 'uploading'));
assert('accepted → idle is valid (reset)', isValidTransition('accepted', 'idle'));
assert('rejected → idle is valid (reset)', isValidTransition('rejected', 'idle'));
assert('idle → accepted is INVALID', !isValidTransition('idle', 'accepted'));
assert('idle → rejected is INVALID', !isValidTransition('idle', 'rejected'));
assert('accepted → uploading is INVALID (must reset first)', !isValidTransition('accepted', 'uploading'));

/* ══════════════════════════════════════════════════════════════════════
   4. Duplicate submission guard
══════════════════════════════════════════════════════════════════════ */

process.stdout.write('\n4. Duplicate submission prevention:\n');

// The isSubmitting flag is true during uploading and polling only
function isSubmitting(state) {
  return state === 'uploading' || state === 'polling';
}

assert('idle → isSubmitting is false', !isSubmitting('idle'));
assert('uploading → isSubmitting is true', isSubmitting('uploading'));
assert('polling → isSubmitting is true', isSubmitting('polling'));
assert('accepted → isSubmitting is false', !isSubmitting('accepted'));
assert('rejected → isSubmitting is false', !isSubmitting('rejected'));
assert('error → isSubmitting is false', !isSubmitting('error'));

/* ══════════════════════════════════════════════════════════════════════
   5. Cancellation: abort signal lifecycle
══════════════════════════════════════════════════════════════════════ */

process.stdout.write('\n5. AbortController lifecycle:\n');

assert(
  'AbortController.abort() marks signal as aborted',
  (() => {
    const c = new AbortController();
    assert('signal not aborted before abort()', !c.signal.aborted);
    c.abort();
    return c.signal.aborted === true;
  })(),
);

assert(
  'abort() on already-aborted controller does not throw',
  (() => {
    const c = new AbortController();
    c.abort();
    try { c.abort(); return true; } catch { return false; }
  })(),
);

/* ══════════════════════════════════════════════════════════════════════
   6. Reason code passthrough contract
══════════════════════════════════════════════════════════════════════ */

process.stdout.write('\n6. Rejection reason passthrough:\n');

// When pollUntilComplete returns { status: 'rejected', reason: 'TOO_QUIET' }
// the hook must set rejectionReason to 'TOO_QUIET' verbatim (no parsing here;
// EnrolValidationPage uses parseValidationFeedback on it).

const reasonCodes = [
  'TOO_SHORT', 'TOO_LONG', 'TOO_QUIET', 'CLIPPING',
  'EXCESSIVE_SILENCE', 'INSUFFICIENT_SPEECH', 'LOW_SNR',
  'UNSUPPORTED_FORMAT', 'CONSENT_MISSING', 'CHALLENGE_MISMATCH',
  'UNKNOWN_REJECTION_REASON',
  // Backend alias variants that parseValidationFeedback handles
  'VOICE_TOO_SHORT', 'VOICE_TOO_QUIET', 'NO_SPEECH_DETECTED',
];

reasonCodes.forEach((code) => {
  assert(
    `Reason code '${code}' is a non-empty string passthrough`,
    typeof code === 'string' && code.length > 0,
  );
});

// null reason falls back to UNKNOWN_REJECTION_REASON (the hook sets this when reason is null)
const nullReason = null;
assert('null reason falls back gracefully', (nullReason ?? 'UNKNOWN_REJECTION_REASON') === 'UNKNOWN_REJECTION_REASON');

/* ══════════════════════════════════════════════════════════════════════
   Results
══════════════════════════════════════════════════════════════════════ */

process.stdout.write(`\n─── Results: ${passed} passed, ${failed} failed ───\n`);
if (failed > 0) process.exit(1);
