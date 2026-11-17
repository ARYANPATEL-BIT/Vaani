/**
 * studioState.js -- which "view" the Studio page shows, as a pure function
 * of values the hooks already expose. No React, no browser: node tests it
 * (studioState.test.js).
 *
 * Views: standby (no session), tuning (connecting), offair (mic or
 * connection failure), ready, listening, thinking, speaking, cut.
 */

/**
 * @param {object} s
 * @param {string} s.wsStatus   useAudioCapture: disconnected|connecting|connected|ready|error
 * @param {string} s.turnState  useTurnState: idle|listening|thinking|speaking|cancelling
 * @param {boolean} s.fatal     mic denied, connection dropped or socket error
 * @param {boolean} s.cutLatched the page saw a barge-in and no new reply yet
 * @returns {string} a key of VIEWS in talkContent.js
 */
export function viewFor({ wsStatus, turnState, fatal, cutLatched }) {
  if (wsStatus === 'connecting' || wsStatus === 'connected') return 'tuning';
  if (wsStatus !== 'ready') return fatal || wsStatus === 'error' ? 'offair' : 'standby';
  if (turnState === 'cancelling' || cutLatched) return 'cut';
  if (turnState === 'listening' || turnState === 'thinking' || turnState === 'speaking') return turnState;
  return 'ready';
}

/**
 * The CUT latch. A barge-in shows CUT from the moment the page hears of it
 * (turn.state cancelling or audio.flush) until the next reply begins.
 * The server always goes cancelling -> listening (backend/vaani/turn_state.py),
 * so CUT stays through the user's new words and clears at thinking, speaking
 * or idle.
 */
export function cutStillLatched(turnState) {
  return turnState === 'cancelling' || turnState === 'listening';
}

/** True if this server message means a reply was cut off. */
export function isCutMessage(msg) {
  if (!msg || typeof msg !== 'object') return false;
  return msg.type === 'audio.flush' || (msg.type === 'turn.state' && msg.state === 'cancelling');
}

/** Seconds -> "MM:SS.cc" (the tape's timecodes). */
export function timecode(seconds) {
  const cs = Math.round(Math.max(0, seconds) * 100);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(Math.floor(cs / 6000))}:${pad(Math.floor(cs / 100) % 60)}.${pad(cs % 100)}`;
}

/** The last `max` characters of a long line, starting at a word, with "…". */
export function tail(text, max) {
  if (!text || text.length <= max) return text || '';
  const cut = text.slice(-max);
  // If the cut fell mid-word, drop that partial word.
  const startsAtWord = text[text.length - max - 1] === ' ';
  const space = cut.indexOf(' ');
  const rest = startsAtWord || space < 0 ? cut : cut.slice(space + 1);
  return `…${rest.trimStart()}`;
}
