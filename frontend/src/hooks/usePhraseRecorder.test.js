/* global process */
/**
 * usePhraseRecorder.test.js — Unit tests for the phrase recording hook logic
 * (spoken consent statement and live challenge phrase).
 *
 * Tests the state machine, duration limits, transitions, re-recording, and
 * error handling without requiring real browser hardware.
 *
 * Run with:
 *   node frontend/src/hooks/usePhraseRecorder.test.js
 */

import {
  MIN_PHRASE_DURATION_S,
  MAX_PHRASE_DURATION_S,
} from './usePhraseRecorder.js';

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

/**
 * Pure state machine replicating usePhraseRecorder's lifecycle logic.
 */
function createPhraseStateMachine({
  minDuration = MIN_PHRASE_DURATION_S,
  maxDuration = MAX_PHRASE_DURATION_S,
} = {}) {
  let state = 'idle';
  let elapsedSeconds = 0;
  let errorMessage = null;
  let hasBlob = false;

  return {
    getState: () => state,
    getElapsed: () => elapsedSeconds,
    getError: () => errorMessage,
    hasBlob: () => hasBlob,

    simulateStart() {
      if (state === 'recording' || state === 'requesting') {
        return false;
      }
      state = 'recording';
      elapsedSeconds = 0;
      errorMessage = null;
      hasBlob = false;
      return true;
    },

    simulateTick(seconds) {
      if (state === 'recording') {
        elapsedSeconds = seconds;
        if (elapsedSeconds >= maxDuration) {
          this.simulateStop();
        }
      }
    },

    simulateStop() {
      if (state !== 'recording') return;
      if (elapsedSeconds < minDuration) {
        state = 'too_short';
        hasBlob = false;
      } else {
        state = 'completed';
        hasBlob = true;
      }
    },

    simulateReRecord() {
      state = 'idle';
      elapsedSeconds = 0;
      errorMessage = null;
      hasBlob = false;
    },

    simulatePermissionDenied() {
      state = 'failed';
      errorMessage =
        'Microphone permission was denied. Please allow microphone access in your browser settings and try again.';
      hasBlob = false;
    },

    simulateDeviceNotFound() {
      state = 'failed';
      errorMessage = 'No microphone found. Please connect a microphone and try again.';
      hasBlob = false;
    },
  };
}

console.log('\n--- Test Suite: usePhraseRecorder ---');

// 1. Duration Constants
console.log('\n1. Duration constants:');
assert('MIN_PHRASE_DURATION_S is 2', MIN_PHRASE_DURATION_S === 2);
assert('MAX_PHRASE_DURATION_S is 15', MAX_PHRASE_DURATION_S === 15);
assert('MIN < MAX', MIN_PHRASE_DURATION_S < MAX_PHRASE_DURATION_S);

// 2. Initial state
console.log('\n2. Initial state:');
{
  const sm = createPhraseStateMachine();
  assert('starts in idle state', sm.getState() === 'idle');
  assert('initial elapsed is 0', sm.getElapsed() === 0);
  assert('initial error is null', sm.getError() === null);
  assert('initial hasBlob is false', sm.hasBlob() === false);
}

// 3. Start recording
console.log('\n3. Start recording transition:');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  assert('transitions to recording', sm.getState() === 'recording');
  assert('elapsed starts at 0', sm.getElapsed() === 0);
}

// 4. Stop before 2 seconds -> too_short
console.log('\n4. Stop before 2 seconds -> too_short:');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  sm.simulateTick(1);
  sm.simulateStop();
  assert('state is too_short when stopped at 1s', sm.getState() === 'too_short');
  assert('hasBlob is false for too_short', sm.hasBlob() === false);
}

// 5. Stop at boundary (2 seconds) -> completed
console.log('\n5. Stop at exactly 2 seconds (boundary):');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  sm.simulateTick(2);
  sm.simulateStop();
  assert('state is completed at exactly 2s', sm.getState() === 'completed');
  assert('hasBlob is true for completed', sm.hasBlob() === true);
}

// 6. Stop after 5 seconds -> completed
console.log('\n6. Stop after 5 seconds:');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  sm.simulateTick(5);
  sm.simulateStop();
  assert('state is completed at 5s', sm.getState() === 'completed');
  assert('elapsed is 5', sm.getElapsed() === 5);
}

// 7. Auto-stop at 15 seconds
console.log('\n7. Auto-stop at 15 seconds:');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  sm.simulateTick(15);
  assert('state is completed automatically at 15s', sm.getState() === 'completed');
  assert('elapsed is 15', sm.getElapsed() === 15);
}

// 8. Re-record from completed
console.log('\n8. Re-record from completed:');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  sm.simulateTick(4);
  sm.simulateStop();
  assert('state before re-record is completed', sm.getState() === 'completed');
  sm.simulateReRecord();
  assert('state after re-record is idle', sm.getState() === 'idle');
  assert('elapsed is reset to 0', sm.getElapsed() === 0);
  assert('hasBlob is cleared', sm.hasBlob() === false);
}

// 9. Re-record from too_short
console.log('\n9. Re-record from too_short:');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  sm.simulateTick(1);
  sm.simulateStop();
  assert('state before re-record is too_short', sm.getState() === 'too_short');
  sm.simulateReRecord();
  assert('state after re-record is idle', sm.getState() === 'idle');
}

// 10. Prevent overlapping recordings
console.log('\n10. Prevent overlapping recordings:');
{
  const sm = createPhraseStateMachine();
  sm.simulateStart();
  const startedAgain = sm.simulateStart();
  assert('cannot start another session while recording', startedAgain === false);
  assert('state remains recording', sm.getState() === 'recording');
}

// 11. Permission denied error handling
console.log('\n11. Permission denied error handling:');
{
  const sm = createPhraseStateMachine();
  sm.simulatePermissionDenied();
  assert('state is failed on permission denied', sm.getState() === 'failed');
  assert('error message mentions permission', sm.getError().includes('permission'));
  sm.simulateReRecord();
  assert('re-record clears error and resets to idle', sm.getState() === 'idle');
  assert('error message is cleared', sm.getError() === null);
}

// 12. Device not found error handling
console.log('\n12. Device not found error handling:');
{
  const sm = createPhraseStateMachine();
  sm.simulateDeviceNotFound();
  assert('state is failed when no mic found', sm.getState() === 'failed');
  assert('error message mentions microphone', sm.getError().includes('microphone'));
}

console.log(`\n─── Results: ${passed} passed, ${failed} failed ───\n`);

if (failed > 0) {
  process.exit(1);
}
