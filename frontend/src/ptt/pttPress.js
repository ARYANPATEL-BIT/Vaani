/**
 * pttPress.js — one push-to-talk press, as a small state machine
 * (docs/contracts.md §2.8).
 *
 * A press goes idle -> holding -> stopping -> idle:
 * - start(): idle -> holding. Sends ptt.start. Mic frames may now be sent.
 * - stop(): holding -> stopping. Asks the AudioWorklet for its last, partial
 *   frame. Frames still flow: they are the end of the user's speech.
 * - lastFrameSent(): stopping -> idle. The worklet has handed over its last
 *   frame, so every frame of the press is already on the socket; only now is
 *   ptt.end sent. Frames on one WebSocket arrive in the order they were sent,
 *   so the server gets the whole press before ptt.end.
 *
 * Anything else is ignored: speak while holding or stopping (a held key
 * repeats its keydown), stop while idle.
 *
 * FALLBACK: if the worklet's answer has not come `fallbackMs` after stop
 * (for example, the audio thread is stalled), ptt.end is sent anyway with a
 * warning, so a press can never stay open until the server's 30 s cap.
 *
 * No React and no browser APIs here, so node can test it (pttPress.test.js).
 * The timer functions are passed in for the same reason.
 */

export const PRESS_STATES = {
  IDLE: 'idle',
  HOLDING: 'holding',
  STOPPING: 'stopping',
};

/**
 * @param {object} deps
 * @param {function(object): void} deps.send - sends one JSON control message.
 * @param {function(): void} deps.requestLastFrame - asks the worklet for its last frame.
 * @param {number} deps.fallbackMs - how long to wait for the worklet's answer.
 * @param {function(string): void} [deps.onChange] - hears every state change.
 * @param {function} [deps.setTimer] - setTimeout, or a fake in tests.
 * @param {function} [deps.clearTimer] - clearTimeout, or a fake in tests.
 * @param {function(string): void} [deps.warn] - console.warn, or a fake in tests.
 */
export function createPttPress({
  send,
  requestLastFrame,
  fallbackMs,
  onChange = () => {},
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  warn = (text) => console.warn(text),
}) {
  let state = PRESS_STATES.IDLE;
  let timer = null;

  function moveTo(next) {
    state = next;
    onChange(next);
  }

  // The one place ptt.end is sent: from the worklet's answer or the fallback.
  function end() {
    timer = null;
    moveTo(PRESS_STATES.IDLE);
    send({ type: 'ptt.end' });
  }

  return {
    get state() {
      return state;
    },

    /** True while mic frames belong to a press: holding, and while stopping. */
    sendsFrames() {
      return state !== PRESS_STATES.IDLE;
    },

    /** Speak pressed. Returns true if a press opened. */
    start() {
      if (state !== PRESS_STATES.IDLE) return false;
      // State BEFORE the send: a frame handled right after must already pass.
      moveTo(PRESS_STATES.HOLDING);
      send({ type: 'ptt.start' });
      return true;
    },

    /** Stop pressed. Returns true if the press began to close. */
    stop() {
      if (state !== PRESS_STATES.HOLDING) return false;
      moveTo(PRESS_STATES.STOPPING);
      requestLastFrame();
      timer = setTimer(() => {
        warn(`[pttPress] no last-frame answer from the worklet after ${fallbackMs} ms; sending ptt.end anyway`);
        end();
      }, fallbackMs);
      return true;
    },

    /** The worklet's answer: its last frame has been handed over. */
    lastFrameSent() {
      // Late, after the fallback already ended the press: nothing to do.
      if (state !== PRESS_STATES.STOPPING) return;
      clearTimer(timer);
      end();
    },

    /** Session over: drop the press without sending anything. */
    reset() {
      if (timer !== null) clearTimer(timer);
      timer = null;
      if (state !== PRESS_STATES.IDLE) moveTo(PRESS_STATES.IDLE);
    },
  };
}
