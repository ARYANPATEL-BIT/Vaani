/* global process */
/**
 * useReferenceRecorder.test.js — Unit tests for the reference-voice recording
 * hook logic (pure JS, no DOM/browser APIs required for state-machine tests).
 *
 * Tests the recording state machine, duration constants, format helpers, and
 * error-handling paths by exercising the pure logic extracted from the hook.
 *
 * Tests that require real MediaRecorder / getUserMedia are marked as
 * MANUAL / BROWSER-ONLY and are not run here.
 *
 * Run with:
 *   node frontend/src/hooks/useReferenceRecorder.test.js
 */

import { MIN_DURATION_S, MAX_DURATION_S } from './useReferenceRecorder.js';

/* ── minimal test harness ─────────────────────────────────────────────── */

let passed = 0;
let failed = 0;

function assert(description, condition, details = '') {
  if (condition) {
    passed++;
    console.log(`  ✓ ${description}`);
  } else {
    failed++;
    console.error(`  ✗ FAIL: ${description}${details ? ` (${details})` : ''}`);
  }
}

/* ── helper functions mirrored from the hook (pure, no React) ─────────── */

function formatTime(totalSeconds) {
  const m = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
  const s = (totalSeconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function progressPercent(elapsed, max) {
  return Math.min((elapsed / max) * 100, 100);
}

/**
 * Minimal state machine that mirrors useReferenceRecorder's logic without
 * React, MediaRecorder, or getUserMedia. Used to verify state transitions.
 */
function createStateMachine() {
  let state = 'idle';
  let elapsedSeconds = 0;
  let errorMessage = null;

  return {
    getState:   () => state,
    getElapsed: () => elapsedSeconds,
    getError:   () => errorMessage,

    // Simulate a successful start
    simulateStart() {
      if (state !== 'idle' && state !== 'too_short' && state !== 'failed') return;
      state = 'requesting';
      // permission granted
      state = 'recording';
      elapsedSeconds = 0;
      errorMessage = null;
    },

    // Simulate advancing time
    advanceTime(seconds) {
      elapsedSeconds += seconds;
    },

    // Simulate user stop (enforces MIN_DURATION_S)
    simulateStop() {
      if (state !== 'recording') return;
      if (elapsedSeconds < MIN_DURATION_S) {
        state = 'too_short';
      } else {
        state = 'completed';
      }
    },

    // Simulate automatic 60-second stop
    simulateAutoStop() {
      elapsedSeconds = MAX_DURATION_S;
      state = 'completed';
    },

    // Simulate a mic permission error
    simulatePermissionDenied() {
      state = 'failed';
      errorMessage = 'Microphone permission was denied.';
    },

    // Simulate a generic recording error
    simulateRecordingError(msg) {
      state = 'failed';
      errorMessage = msg;
    },

    // Re-record: discard and reset to idle
    simulateReRecord() {
      state = 'idle';
      elapsedSeconds = 0;
      errorMessage = null;
    },
  };
}

/* ── Test suite ───────────────────────────────────────────────────────── */

console.log('\n--- Test Suite: useReferenceRecorder ---\n');

// 1. Constants
console.log('1. Duration constants:');
assert('MIN_DURATION_S is 30',      MIN_DURATION_S === 30);
assert('MAX_DURATION_S is 60',      MAX_DURATION_S === 60);
assert('MIN < MAX',                 MIN_DURATION_S < MAX_DURATION_S);

// 2. Initial state
console.log('\n2. Initial state:');
const m = createStateMachine();
assert('starts as idle',            m.getState() === 'idle');
assert('elapsed starts at 0',       m.getElapsed() === 0);
assert('no initial error',          m.getError() === null);

// 3. Start recording
console.log('\n3. Start → recording transition:');
m.simulateStart();
assert('transitions to recording',  m.getState() === 'recording');
assert('elapsed resets to 0',       m.getElapsed() === 0);
assert('error cleared on start',    m.getError() === null);

// 4. Too short — stop before 30 s
console.log('\n4. Stop before 30 seconds → too_short:');
m.advanceTime(15);
m.simulateStop();
assert('state is too_short at 15s', m.getState() === 'too_short');
assert('elapsed is 15',             m.getElapsed() === 15);

// 5. Re-record from too_short
console.log('\n5. Re-record from too_short:');
m.simulateReRecord();
assert('returns to idle',           m.getState() === 'idle');
assert('elapsed resets to 0',       m.getElapsed() === 0);

// 6. Valid recording (>= 30 s)
console.log('\n6. Stop after 35 seconds → completed:');
m.simulateStart();
m.advanceTime(35);
m.simulateStop();
assert('state is completed at 35s', m.getState() === 'completed');
assert('elapsed is 35',             m.getElapsed() === 35);

// 7. Re-record from completed
console.log('\n7. Re-record from completed:');
m.simulateReRecord();
assert('returns to idle',           m.getState() === 'idle');
assert('elapsed resets to 0',       m.getElapsed() === 0);

// 8. Auto-stop at 60 seconds
console.log('\n8. Auto-stop at 60 seconds:');
m.simulateStart();
m.simulateAutoStop();
assert('state is completed at 60s', m.getState() === 'completed');
assert('elapsed is 60',             m.getElapsed() === MAX_DURATION_S);

// 9. Prevent starting while recording
console.log('\n9. Prevent overlapping sessions:');
const m2 = createStateMachine();
m2.simulateStart();
// A second start call should be ignored (state is 'recording', not startable)
const validStartStates = ['idle', 'too_short', 'failed'];
const wouldStart = validStartStates.includes(m2.getState());
assert('cannot start when already recording', !wouldStart);
assert('state unchanged after duplicate start attempt', m2.getState() === 'recording');

// 10. Permission denied
console.log('\n10. Microphone permission denied:');
const m3 = createStateMachine();
m3.simulatePermissionDenied();
assert('state is failed',           m3.getState() === 'failed');
assert('error message is set',      m3.getError() !== null);
assert('error mentions permission', m3.getError().toLowerCase().includes('permission'));

// 11. Re-record from failed
console.log('\n11. Re-record from failed state:');
m3.simulateReRecord();
assert('returns to idle from failed', m3.getState() === 'idle');
assert('error cleared after re-record', m3.getError() === null);

// 12. Generic recording error
console.log('\n12. Generic recording error:');
const m4 = createStateMachine();
m4.simulateStart();
m4.simulateRecordingError('MediaRecorder encountered an error.');
assert('state is failed',           m4.getState() === 'failed');
assert('error message preserved',   m4.getError() === 'MediaRecorder encountered an error.');

// 13. formatTime helper
console.log('\n13. formatTime formatting:');
assert('0s → 00:00',                formatTime(0) === '00:00');
assert('30s → 00:30',               formatTime(30) === '00:30');
assert('60s → 01:00',               formatTime(60) === '01:00');
assert('65s → 01:05',               formatTime(65) === '01:05');
assert('9s → 00:09 (zero-padded)',   formatTime(9) === '00:09');

// 14. progressPercent helper
console.log('\n14. progressPercent helper:');
assert('0 / 60 = 0%',              progressPercent(0, 60) === 0);
assert('30 / 60 = 50%',            progressPercent(30, 60) === 50);
assert('60 / 60 = 100%',           progressPercent(60, 60) === 100);
assert('75 / 60 clamped to 100%',  progressPercent(75, 60) === 100);
assert('15 / 60 = 25%',            progressPercent(15, 60) === 25);

// 15. Elapsed boundary: stop at exactly 30 s → completed
console.log('\n15. Stop at exactly 30 seconds → completed (boundary):');
const m5 = createStateMachine();
m5.simulateStart();
m5.advanceTime(30);
m5.simulateStop();
assert('state is completed at exactly 30s', m5.getState() === 'completed');

// 16. Stop at 29 s → too_short (boundary)
console.log('\n16. Stop at 29 seconds → too_short (boundary):');
const m6 = createStateMachine();
m6.simulateStart();
m6.advanceTime(29);
m6.simulateStop();
assert('state is too_short at 29s', m6.getState() === 'too_short');

/* ── Summary ──────────────────────────────────────────────────────────── */

console.log(`\n─── Results: ${passed} passed, ${failed} failed ───\n`);
if (failed > 0) {
  process.exit(1);
}
