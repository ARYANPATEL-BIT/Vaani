/**
 * verifyState.js — the state machine for the voice verification screen
 * (/enrol/verify, Week 4 Tuesday).
 *
 * A state machine is a fixed list of states plus a rule for each event:
 * "in state X, event E moves you to state Y". An event that has no rule
 * for the current state is ignored (the same state comes back). That is
 * what makes the screen safe: there is exactly one way into 'approved',
 * and it needs the server's confirmation.
 *
 * States (state.status):
 *   loading   — asking the server to render the test sentence.
 *   ready     — the sample is loaded and not playing.
 *   playing   — the <audio> element is playing the sample.
 *   error     — no sample could be loaded; nothing can be played or approved.
 *   approving — "Yes, use this voice" was pressed; waiting for the server.
 *   approved  — the server confirmed the approval. Only now is the voice active.
 *
 * "Record again" is not a state: the page navigates to /enrol/record, which
 * unmounts this screen and throws its state away.
 *
 * This file has no React and no browser APIs, so it runs under plain node
 * (verifyState.test.js). useVoiceVerify.js feeds it events.
 */

export const initialVerifyState = {
  status: 'loading',
  sampleUrl: null,  // object URL of the rendered audio (see useVoiceVerify.js)
  hasPlayed: false, // true once the sample has played to its end at least once
  error: null,      // message shown to the user, or null
};

/**
 * Pure function: (current state, event) -> next state. Never mutates.
 * @param {typeof initialVerifyState} state
 * @param {{ type: string, sampleUrl?: string, error?: string }} event
 */
export function verifyReducer(state, event) {
  switch (event.type) {
    case 'LOAD_OK':
      if (state.status !== 'loading') return state;
      return { ...state, status: 'ready', sampleUrl: event.sampleUrl, error: null };

    case 'LOAD_FAIL':
      if (state.status !== 'loading') return state;
      return { ...state, status: 'error', error: event.error };

    case 'RETRY_LOAD':
      if (state.status !== 'error') return state;
      return initialVerifyState;

    case 'PLAY':
      if (state.status !== 'ready') return state;
      return { ...state, status: 'playing', error: null };

    // The sample reached its end: this is what unlocks approval.
    case 'ENDED':
      if (state.status !== 'playing') return state;
      return { ...state, status: 'ready', hasPlayed: true };

    // Stopped before the end: back to ready, approval still locked
    // unless an earlier play already finished.
    case 'STOPPED':
      if (state.status !== 'playing') return state;
      return { ...state, status: 'ready' };

    // The browser refused or failed to play (e.g. unsupported format).
    case 'PLAY_FAIL':
      if (state.status !== 'playing' && state.status !== 'ready') return state;
      return { ...state, status: 'ready', error: event.error };

    case 'APPROVE':
      if (!canApprove(state)) return state;
      return { ...state, status: 'approving', error: null };

    case 'APPROVE_OK':
      if (state.status !== 'approving') return state;
      return { ...state, status: 'approved', error: null };

    // The server did not confirm: back to ready so the user can try again.
    case 'APPROVE_FAIL':
      if (state.status !== 'approving') return state;
      return { ...state, status: 'ready', error: event.error };

    default:
      return state;
  }
}

/** "Yes, use this voice" is enabled only after one full play, while idle. */
export function canApprove(state) {
  return state.status === 'ready' && state.hasPlayed;
}

/** The play button works only when a sample is loaded and nothing is in flight. */
export function canPlay(state) {
  return state.status === 'ready' || state.status === 'playing';
}
