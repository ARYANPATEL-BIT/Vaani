/* global process */
/**
 * enrolConsent.test.js — Sequence and state contract tests for Week 3 Day 4
 * Enrolment Consent & Live Challenge Phrase flow.
 *
 * Verifies:
 *  - Spoken consent statement wording presence
 *  - Challenge phrase hidden until step 2 (Strict Visibility Guard)
 *  - Strict sequencing (cannot record or view challenge without completed consent)
 *  - Re-recording isolation and sequence preservation
 *  - Both recordings required to proceed to reference recording
 *
 * Run with:
 *   node frontend/src/pages/enrolConsent.test.js
 */

export const SPOKEN_CONSENT_TEXT =
  'I confirm that I am the operator and I consent to Vaani recording my voice for identity enrolment.';

export const CLIENT_CHALLENGE_PHRASE =
  'Vaani verification challenge: Mera naam operator hai aur main identity enrolment verify kar raha hoon.';

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
 * Pure state machine representing the EnrolConsentPage multi-step flow.
 */
function createConsentFlowMachine() {
  let step = 'consent'; // 'consent' | 'challenge' | 'completed'
  let consentRecorded = false;
  let challengeRecorded = false;
  let activeRecording = null; // null | 'consent' | 'challenge'

  return {
    getStep: () => step,
    isConsentRecorded: () => consentRecorded,
    isChallengeRecorded: () => challengeRecorded,
    getActiveRecording: () => activeRecording,

    // Challenge visibility rule: strictly hidden unless on challenge or completed step
    isChallengePhraseVisible() {
      return step === 'challenge' || step === 'completed';
    },

    // Step 1: Consent recording
    startConsentRecording() {
      if (activeRecording !== null) return false; // prevent overlap
      activeRecording = 'consent';
      return true;
    },

    finishConsentRecording(success = true) {
      if (activeRecording !== 'consent') return;
      activeRecording = null;
      if (success) {
        consentRecorded = true;
      }
    },

    // Move to challenge step (Strict sequence guard)
    proceedToChallengeStep() {
      if (!consentRecorded) {
        return false; // cannot proceed without consent
      }
      step = 'challenge';
      return true;
    },

    // Step 2: Challenge recording
    startChallengeRecording() {
      if (step !== 'challenge') return false; // cannot record challenge before step 2
      if (!consentRecorded) return false; // sequence guard
      if (activeRecording !== null) return false; // prevent overlap
      activeRecording = 'challenge';
      return true;
    },

    finishChallengeRecording(success = true) {
      if (activeRecording !== 'challenge') return;
      activeRecording = null;
      if (success) {
        challengeRecorded = true;
        step = 'completed';
      }
    },

    // Re-record consent: MUST reset challenge to maintain strict sequence
    reRecordConsent() {
      if (activeRecording !== null) return;
      consentRecorded = false;
      challengeRecorded = false;
      step = 'consent';
    },

    // Re-record challenge: only resets challenge, preserves consent
    reRecordChallenge() {
      if (activeRecording !== null) return;
      challengeRecorded = false;
      step = 'challenge';
    },

    // Can proceed to reference recording (/enrol/record)
    canProceedToReference() {
      return consentRecorded && challengeRecorded && step === 'completed';
    },
  };
}

console.log('\n--- Test Suite: Enrolment Consent & Challenge Sequence ---');

// 1. Text & Constants
console.log('\n1. Spoken Consent and Challenge Constants:');
assert('SPOKEN_CONSENT_TEXT is defined', typeof SPOKEN_CONSENT_TEXT === 'string');
assert('SPOKEN_CONSENT_TEXT includes "operator"', SPOKEN_CONSENT_TEXT.includes('operator'));
assert('SPOKEN_CONSENT_TEXT includes "consent"', SPOKEN_CONSENT_TEXT.includes('consent'));
assert('SPOKEN_CONSENT_TEXT includes "enrolment"', SPOKEN_CONSENT_TEXT.includes('enrolment'));
assert('CLIENT_CHALLENGE_PHRASE is defined', typeof CLIENT_CHALLENGE_PHRASE === 'string');
assert('CLIENT_CHALLENGE_PHRASE includes "challenge"', CLIENT_CHALLENGE_PHRASE.includes('challenge'));

// 2. Initial state & visibility guard
console.log('\n2. Initial Step & Challenge Visibility Guard:');
{
  const flow = createConsentFlowMachine();
  assert('starts at "consent" step', flow.getStep() === 'consent');
  assert('consent is not recorded initially', flow.isConsentRecorded() === false);
  assert('challenge is not recorded initially', flow.isChallengeRecorded() === false);
  assert('challenge phrase is NOT visible at step 1', flow.isChallengePhraseVisible() === false);
  assert('cannot proceed to reference recording initially', flow.canProceedToReference() === false);
}

// 3. Strict sequence: cannot jump to challenge
console.log('\n3. Strict sequence enforcement (Step 1 -> Step 2):');
{
  const flow = createConsentFlowMachine();
  const advanced = flow.proceedToChallengeStep();
  assert('cannot jump to challenge step before recording consent', advanced === false);
  assert('step remains "consent"', flow.getStep() === 'consent');
  assert('challenge phrase remains hidden', flow.isChallengePhraseVisible() === false);

  const startChallengeDirectly = flow.startChallengeRecording();
  assert('cannot start challenge recording before consent recorded', startChallengeDirectly === false);
}

// 4. Record consent & advance to challenge
console.log('\n4. Record consent and reveal challenge:');
{
  const flow = createConsentFlowMachine();
  flow.startConsentRecording();
  assert('consent recording is active', flow.getActiveRecording() === 'consent');

  // Attempt to start challenge during consent recording
  const overlap = flow.startChallengeRecording();
  assert('cannot start overlapping recording', overlap === false);

  flow.finishConsentRecording(true);
  assert('consent is recorded', flow.isConsentRecorded() === true);
  assert('active recording is cleared', flow.getActiveRecording() === null);
  assert('challenge phrase still hidden until user moves to step 2', flow.isChallengePhraseVisible() === false);

  const advanced = flow.proceedToChallengeStep();
  assert('proceeds to challenge step successfully', advanced === true);
  assert('step is now "challenge"', flow.getStep() === 'challenge');
  assert('challenge phrase is now REVEALED at step 2', flow.isChallengePhraseVisible() === true);
}

// 5. Record challenge and complete flow
console.log('\n5. Record challenge and complete sequence:');
{
  const flow = createConsentFlowMachine();
  flow.startConsentRecording();
  flow.finishConsentRecording(true);
  flow.proceedToChallengeStep();

  flow.startChallengeRecording();
  assert('challenge recording is active', flow.getActiveRecording() === 'challenge');
  flow.finishChallengeRecording(true);

  assert('challenge is recorded', flow.isChallengeRecorded() === true);
  assert('step is completed', flow.getStep() === 'completed');
  assert('can now proceed to reference recording', flow.canProceedToReference() === true);
}

// 6. Re-recording consent preserves strict sequence
console.log('\n6. Re-record consent invalidates challenge:');
{
  const flow = createConsentFlowMachine();
  flow.startConsentRecording();
  flow.finishConsentRecording(true);
  flow.proceedToChallengeStep();
  flow.startChallengeRecording();
  flow.finishChallengeRecording(true);
  assert('both recorded', flow.canProceedToReference() === true);

  // User decides to re-record consent
  flow.reRecordConsent();
  assert('step returns to "consent"', flow.getStep() === 'consent');
  assert('consent is reset', flow.isConsentRecorded() === false);
  assert('challenge is invalidated to preserve strict sequence', flow.isChallengeRecorded() === false);
  assert('challenge phrase is hidden again', flow.isChallengePhraseVisible() === false);
  assert('cannot proceed to reference recording', flow.canProceedToReference() === false);
}

// 7. Re-recording challenge alone keeps consent intact
console.log('\n7. Re-record challenge alone:');
{
  const flow = createConsentFlowMachine();
  flow.startConsentRecording();
  flow.finishConsentRecording(true);
  flow.proceedToChallengeStep();
  flow.startChallengeRecording();
  flow.finishChallengeRecording(true);

  // User re-records challenge
  flow.reRecordChallenge();
  assert('step is "challenge"', flow.getStep() === 'challenge');
  assert('consent remains recorded', flow.isConsentRecorded() === true);
  assert('challenge is reset for retry', flow.isChallengeRecorded() === false);
  assert('challenge phrase remains visible during re-record', flow.isChallengePhraseVisible() === true);
  assert('cannot proceed to reference until challenge is re-recorded', flow.canProceedToReference() === false);

  flow.startChallengeRecording();
  flow.finishChallengeRecording(true);
  assert('can proceed after challenge re-recorded', flow.canProceedToReference() === true);
}

console.log(`\n─── Results: ${passed} passed, ${failed} failed ───\n`);

if (failed > 0) {
  process.exit(1);
}
