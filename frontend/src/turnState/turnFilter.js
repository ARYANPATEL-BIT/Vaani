/**
 * turnFilter.js — drops what still arrives for a flushed turn
 * (docs/contracts.md §2.3 audio.flush, §2.7, §2.8).
 *
 * The contract: once a turn is flushed, frames that still arrive for it
 * must be discarded. A turn is flushed by the server's audio.flush, or
 * locally, the moment the user presses speak over the agent in
 * push-to-talk mode (before the server's audio.flush has come back).
 *
 * Binary audio frames carry no turn_id. They belong to the turn of the
 * latest audio.start, so the filter remembers that turn.
 *
 * What is dropped for a flushed turn: its audio frames, audio.start,
 * audio.end, agent.text and agent.done. What is never dropped: turn.state
 * (it is the server's truth), transcripts (they are the user's own words),
 * errors and audio.flush itself.
 *
 * No React here, so node can test it (turnFilter.test.js).
 */

// Messages that belong to the agent's reply, and so die with a flushed turn.
const REPLY_MESSAGES = new Set(['audio.start', 'audio.end', 'agent.text', 'agent.done']);

export function createTurnFilter() {
  // Every turn flushed in this session. Never emptied: a flushed turn stays
  // flushed, and a session has at most a few hundred turns.
  const flushed = new Set();
  // The turn of the latest audio.start: whose audio the next frame is.
  let audioTurnId = null;

  return {
    /** Mark a turn flushed (server audio.flush, or a local push-to-talk stop). */
    flush(turnId) {
      if (typeof turnId === 'string' && turnId) flushed.add(turnId);
    },

    /** True if this binary audio frame belongs to a flushed turn. */
    dropFrame() {
      return audioTurnId !== null && flushed.has(audioTurnId);
    },

    /** True if this parsed JSON message belongs to a flushed turn. */
    dropMessage(msg) {
      if (msg.type === 'audio.start') {
        // Recorded even when dropped, so that turn's frames are dropped too.
        audioTurnId = typeof msg.turn_id === 'string' ? msg.turn_id : null;
      }
      return REPLY_MESSAGES.has(msg.type) && flushed.has(msg.turn_id);
    },
  };
}
