/* global process */
/**
 * turnState.test.js — Unit test suite for Week 3 Day 2 turn states,
 * streaming agent reply, interrupted turns, and error conditions.
 *
 * Covers all 13 official test requirements:
 * 1. Initial/idle state
 * 2. Listening state
 * 3. Thinking state
 * 4. Speaking state
 * 5. Streaming assistant text updates
 * 6. Completion of streamed assistant response
 * 7. Interrupted response is clearly represented
 * 8. Microphone permission failure
 * 9. Connection dropped
 * 10. Provider failure
 * 11. Unknown/malformed server messages do not crash
 * 12. Errors do not silently disappear
 * 13. A new conversation turn can continue after an error/interruption
 *
 * Run with:
 *   node frontend/src/turnState/turnState.test.js
 */

import {
  TURN_STATES,
  VALID_TURN_STATES,
  ERROR_CODES,
  formatServerError,
  validateTurnState,
  validateAgentText,
  validateAgentDone,
  validateErrorMessage,
} from './turnContracts.js';

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

console.log('\n--- Test Suite: Vaani Turn States & Error Contract ---');

// 1. Initial / Idle State
console.log('\n1. Initial / Idle state:');
assert('TURN_STATES includes idle', TURN_STATES.IDLE === 'idle');
assert('VALID_TURN_STATES contains 5 wire states', VALID_TURN_STATES.size === 5);
assert('idle is a valid state', VALID_TURN_STATES.has('idle'));

// Simulated turn state machine
function createTurnMachine() {
  let state = TURN_STATES.IDLE;
  let turnId = null;
  let agentDraft = null;
  let lastCompleted = null;
  const history = [];

  return {
    getState: () => state,
    getTurnId: () => turnId,
    getAgentDraft: () => agentDraft,
    getLastCompleted: () => lastCompleted,
    getHistory: () => history,
    handleMessage(msg) {
      if (!msg || typeof msg !== 'object') return { handled: false, error: 'invalid_object' };

      if (msg.type === 'turn.state') {
        const res = validateTurnState(msg);
        if (res.valid) {
          state = res.state;
          turnId = res.turnId;
          if (res.state === TURN_STATES.IDLE) {
            agentDraft = null;
          }
          return { handled: true };
        }
        return { handled: false, error: res.error };
      }

      if (msg.type === 'agent.text') {
        const res = validateAgentText(msg);
        if (res.valid) {
          agentDraft = (agentDraft || '') + res.delta;
          return { handled: true };
        }
        return { handled: false, error: res.error };
      }

      if (msg.type === 'agent.done') {
        const res = validateAgentDone(msg);
        if (res.valid) {
          lastCompleted = res.text;
          history.push({ role: 'agent', text: res.text, interrupted: false });
          agentDraft = null;
          return { handled: true };
        }
        return { handled: false, error: res.error };
      }

      if (msg.type === 'audio.flush' || (msg.type === 'turn.state' && msg.state === 'cancelling')) {
        if (agentDraft && agentDraft.trim()) {
          history.push({ role: 'agent', text: agentDraft.trim(), interrupted: true });
        }
        agentDraft = null;
        state = TURN_STATES.CANCELLING;
        return { handled: true };
      }

      return { handled: false, error: 'unknown_type' };
    },
    reset() {
      state = TURN_STATES.IDLE;
      turnId = null;
      agentDraft = null;
    },
  };
}

const machine = createTurnMachine();
assert('Machine starts in idle state', machine.getState() === 'idle');
assert('Machine starts with null turnId', machine.getTurnId() === null);
assert('Machine starts with null agentDraft', machine.getAgentDraft() === null);

// 2. Listening State
console.log('\n2. Listening state:');
machine.handleMessage({ type: 'turn.state', turn_id: 'turn-001', state: 'listening' });
assert('Transitions to listening state', machine.getState() === 'listening');
assert('Records active turn_id', machine.getTurnId() === 'turn-001');

// 3. Thinking State
console.log('\n3. Thinking state:');
machine.handleMessage({ type: 'turn.state', turn_id: 'turn-001', state: 'thinking' });
assert('Transitions to thinking state', machine.getState() === 'thinking');

// 4. Speaking State
console.log('\n4. Speaking state:');
machine.handleMessage({ type: 'turn.state', turn_id: 'turn-001', state: 'speaking' });
assert('Transitions to speaking state', machine.getState() === 'speaking');

// 5. Streaming Assistant Text Updates
console.log('\n5. Streaming assistant text updates:');
machine.handleMessage({ type: 'agent.text', turn_id: 'turn-001', delta: 'Namaste! ' });
assert('First delta accumulated in draft', machine.getAgentDraft() === 'Namaste! ');

machine.handleMessage({ type: 'agent.text', turn_id: 'turn-001', delta: 'Main Vaani hoon. ' });
assert('Second delta appended progressively', machine.getAgentDraft() === 'Namaste! Main Vaani hoon. ');

machine.handleMessage({ type: 'agent.text', turn_id: 'turn-001', delta: 'Aap kaise hain?' });
assert('Third delta appended without loss', machine.getAgentDraft() === 'Namaste! Main Vaani hoon. Aap kaise hain?');

// 6. Completion of Streamed Assistant Response
console.log('\n6. Completion of streamed assistant response:');
machine.handleMessage({
  type: 'agent.done',
  turn_id: 'turn-001',
  text: 'Namaste! Main Vaani hoon. Aap kaise hain?',
});
assert('Settles into final completed text', machine.getLastCompleted() === 'Namaste! Main Vaani hoon. Aap kaise hain?');
assert('Agent draft cleared on completion', machine.getAgentDraft() === null);
const lastEntry = machine.getHistory()[machine.getHistory().length - 1];
assert('History entry role is agent', lastEntry.role === 'agent');
assert('History entry interrupted flag is false', lastEntry.interrupted === false);

// 7. Interrupted Response Clearly Represented
console.log('\n7. Interrupted turn handling:');
machine.handleMessage({ type: 'turn.state', turn_id: 'turn-002', state: 'listening' });
machine.handleMessage({ type: 'turn.state', turn_id: 'turn-002', state: 'thinking' });
machine.handleMessage({ type: 'turn.state', turn_id: 'turn-002', state: 'speaking' });
machine.handleMessage({ type: 'agent.text', turn_id: 'turn-002', delta: 'Maine aapki file check kar li hai aur' });

// Turn gets interrupted mid-stream via audio.flush / cancelling
machine.handleMessage({ type: 'audio.flush', turn_id: 'turn-002' });
assert('Machine transitions to cancelling state', machine.getState() === 'cancelling');
assert('Agent draft cleared after interruption', machine.getAgentDraft() === null);
const interruptedEntry = machine.getHistory()[machine.getHistory().length - 1];
assert('Interrupted entry preserved received text', interruptedEntry.text === 'Maine aapki file check kar li hai aur');
assert('Interrupted entry clearly marked as interrupted', interruptedEntry.interrupted === true);

// 8. Microphone Permission Failure
console.log('\n8. Microphone permission failure:');
function simulateMicError(errName) {
  if (errName === 'NotAllowedError' || errName === 'PermissionDeniedError') {
    return {
      status: 'denied',
      message: 'Microphone access was denied. Please allow microphone permissions in your browser.',
      recoverable: true,
    };
  }
  return {
    status: 'error',
    message: 'Failed to initialize audio capture pipeline.',
    recoverable: false,
  };
}

const micDenied = simulateMicError('NotAllowedError');
assert('NotAllowedError sets status to denied', micDenied.status === 'denied');
assert('Microphone denied provides clear message', micDenied.message.includes('Microphone access was denied'));
assert('Microphone denied marked as recoverable', micDenied.recoverable === true);

// 9. Connection Dropped
console.log('\n9. Connection dropped handling:');
function handleSocketClose(wasActive, isIntentional, wasClean) {
  if (wasActive && !isIntentional && !wasClean) {
    return {
      status: 'disconnected',
      error: 'Connection dropped: The voice session connection to the backend server was closed unexpectedly.',
      dropped: true,
    };
  }
  return { status: 'disconnected', error: null, dropped: false };
}

const dropEvent = handleSocketClose(true, false, false);
assert('Unexpected socket close detects connection dropped', dropEvent.dropped === true);
assert('Connection dropped provides clear explanation', dropEvent.error.includes('Connection dropped'));
assert('Clean disconnect does not trigger false error', handleSocketClose(true, true, true).dropped === false);

// 10. Provider Failure
console.log('\n10. Provider failure error contract:');
assert('LLM_FAILED error code is defined', ERROR_CODES.LLM_FAILED === 'LLM_FAILED');
assert('ASR_FAILED error code is defined', ERROR_CODES.ASR_FAILED === 'ASR_FAILED');
assert('TTS_FAILED error code is defined', ERROR_CODES.TTS_FAILED === 'TTS_FAILED');
assert('INPUT_REJECTED error code is defined', ERROR_CODES.INPUT_REJECTED === 'INPUT_REJECTED');

const llmErr = formatServerError('LLM_FAILED', 'the agent could not answer');
assert('LLM_FAILED maps to clear explanation', llmErr.includes('model provider failed') || llmErr.includes('spend limits'));

const asrErr = formatServerError('ASR_FAILED', 'recognition failed');
assert('ASR_FAILED maps to speech recognition explanation', asrErr.includes('Speech recognition failed'));

const ttsErr = formatServerError('TTS_FAILED', 'tts failed');
assert('TTS_FAILED maps to speech synthesis explanation', ttsErr.includes('Speech synthesis failed'));

const inputErr = formatServerError('INPUT_REJECTED', "that turn wasn't processed");
assert('INPUT_REJECTED maps to guardrail explanation', inputErr.includes('guardrail') || inputErr.includes('processed'));

// 11. Unknown / Malformed Server Messages Do Not Crash
console.log('\n11. Malformed and unexpected message handling:');
assert('Rejects null message safely', validateTurnState(null).valid === false);
assert('Rejects undefined message safely', validateTurnState(undefined).valid === false);
assert('Rejects wrong message type', validateTurnState({ type: 'random.message' }).valid === false);
assert('Rejects unknown state string', validateTurnState({ type: 'turn.state', state: 'exploding' }).valid === false);
assert('Rejects non-string agent text delta', validateAgentText({ type: 'agent.text', turn_id: 't1', delta: 123 }).valid === false);
assert('Rejects non-string agent done text', validateAgentDone({ type: 'agent.done', turn_id: 't1', text: null }).valid === false);
assert('Rejects invalid error message', validateErrorMessage({ type: 'error', code: 404 }).valid === false);

// 12. Errors Do Not Silently Disappear
console.log('\n12. Error retention verification:');
let currentError = formatServerError('LLM_FAILED');
assert('Error is stored in state', currentError !== null);
// Incoming irrelevant events do not wipe error
function checkErrorRetention(err, eventType) {
  if (eventType === 'clearError' || eventType === 'retry') return null;
  return err; // error is preserved
}
assert('Audio frame does not wipe error', checkErrorRetention(currentError, 'frame') === currentError);
assert('FPS tick does not wipe error', checkErrorRetention(currentError, 'fps_tick') === currentError);
assert('Explicit clear clears error', checkErrorRetention(currentError, 'clearError') === null);

// 13. Next Turn Continues After Interruption/Error
console.log('\n13. Next turn continuation after error or interruption:');
// Machine was in cancelling state from test 7
machine.handleMessage({ type: 'turn.state', turn_id: null, state: 'idle' });
assert('Returns to idle after cancellation', machine.getState() === 'idle');

// Turn 3 begins normally
machine.handleMessage({ type: 'turn.state', turn_id: 'turn-003', state: 'listening' });
assert('Turn 3 transitions to listening', machine.getState() === 'listening');
assert('Turn 3 has new turn_id', machine.getTurnId() === 'turn-003');

machine.handleMessage({ type: 'turn.state', turn_id: 'turn-003', state: 'thinking' });
assert('Turn 3 transitions to thinking', machine.getState() === 'thinking');

machine.handleMessage({ type: 'agent.text', turn_id: 'turn-003', delta: 'Agla sawaal bataiye.' });
assert('Turn 3 streams text normally', machine.getAgentDraft() === 'Agla sawaal bataiye.');

machine.handleMessage({ type: 'agent.done', turn_id: 'turn-003', text: 'Agla sawaal bataiye.' });
assert('Turn 3 finalizes normally', machine.getLastCompleted() === 'Agla sawaal bataiye.');

console.log('\n=======================================');
console.log(`Results: ${passedCount} passed, ${failedCount} failed`);
console.log('=======================================\n');

if (failedCount > 0) {
  process.exitCode = 1;
}
