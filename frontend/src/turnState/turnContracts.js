/**
 * turnContracts.js — Shared contract definitions, validators, and error formatters
 * for conversational turn states and error conditions.
 *
 * Wire protocol source:
 * - backend/vaani/protocol.py (ErrorCode, TurnState, AgentText, AgentDone, TurnStateMessage)
 * - backend/vaani/turn_state.py (turn state transitions)
 * - docs/contracts.md §2.3 (Error codes), §2.4 (Transcripts), §2.5 (Agent turn)
 */

export const TURN_STATES = {
  IDLE: 'idle',
  LISTENING: 'listening',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  CANCELLING: 'cancelling',
};

export const VALID_TURN_STATES = new Set(Object.values(TURN_STATES));

/**
 * Stable wire error codes from backend/vaani/protocol.py ErrorCode.
 */
export const ERROR_CODES = {
  SESSION_NOT_STARTED: 'SESSION_NOT_STARTED',
  UNSUPPORTED_FORMAT: 'UNSUPPORTED_FORMAT',
  BAD_FRAME_SIZE: 'BAD_FRAME_SIZE',
  BAD_MESSAGE: 'BAD_MESSAGE',
  UNKNOWN_MESSAGE_TYPE: 'UNKNOWN_MESSAGE_TYPE',
  ASR_FAILED: 'ASR_FAILED',
  LLM_FAILED: 'LLM_FAILED',
  INPUT_REJECTED: 'INPUT_REJECTED',
  TTS_FAILED: 'TTS_FAILED',
};

/**
 * Human-readable error explanations mapped directly from docs/contracts.md §2.3.
 */
export const ERROR_DETAILS = {
  [ERROR_CODES.ASR_FAILED]: 'Speech recognition failed to transcribe your audio for this turn.',
  [ERROR_CODES.LLM_FAILED]: 'The agent could not answer: the model provider failed, returned an empty reply, or exceeded spend limits.',
  [ERROR_CODES.INPUT_REJECTED]: "That turn wasn't processed by the input guardrail.",
  [ERROR_CODES.TTS_FAILED]: 'Speech synthesis failed to voice the response.',
  [ERROR_CODES.SESSION_NOT_STARTED]: 'Audio frame or message arrived before session start was confirmed.',
  [ERROR_CODES.UNSUPPORTED_FORMAT]: 'Audio configuration mismatch with backend requirement (16 kHz mono 20 ms).',
  [ERROR_CODES.BAD_FRAME_SIZE]: 'Binary audio frame size mismatch (expected 640 bytes).',
  [ERROR_CODES.BAD_MESSAGE]: 'Malformed request or unknown persona requested.',
  [ERROR_CODES.UNKNOWN_MESSAGE_TYPE]: 'Unhandled message type sent to backend gateway.',
};

/**
 * Format a server error code and backend message into an informative user-facing explanation.
 *
 * @param {string} code - Stable error code from protocol.
 * @param {string} [serverMessage] - Optional message sent by backend.
 * @returns {string} User-facing explanation string.
 */
export function formatServerError(code, serverMessage) {
  if (code && ERROR_DETAILS[code]) {
    return ERROR_DETAILS[code];
  }
  if (typeof serverMessage === 'string' && serverMessage.trim()) {
    return serverMessage.trim();
  }
  return 'An unexpected service failure occurred. Please retry.';
}

/**
 * Validate incoming turn.state control message.
 *
 * @param {object} msg - Parsed JSON message from server.
 * @returns {{ valid: boolean, state?: string, turnId?: string|null, error?: string }}
 */
export function validateTurnState(msg) {
  if (!msg || typeof msg !== 'object') {
    return { valid: false, error: 'Message must be an object' };
  }
  if (msg.type !== 'turn.state') {
    return { valid: false, error: `Invalid message type '${msg.type}', expected 'turn.state'` };
  }
  if (!VALID_TURN_STATES.has(msg.state)) {
    return { valid: false, error: `Invalid turn state '${msg.state}'` };
  }
  return {
    valid: true,
    state: msg.state,
    turnId: msg.turn_id ?? null,
  };
}

/**
 * Validate incoming agent.text streamed delta message.
 *
 * @param {object} msg - Parsed JSON message.
 * @returns {{ valid: boolean, delta?: string, turnId?: string, error?: string }}
 */
export function validateAgentText(msg) {
  if (!msg || typeof msg !== 'object') {
    return { valid: false, error: 'Message must be an object' };
  }
  if (msg.type !== 'agent.text') {
    return { valid: false, error: `Invalid message type '${msg.type}', expected 'agent.text'` };
  }
  if (typeof msg.turn_id !== 'string' || !msg.turn_id) {
    return { valid: false, error: 'Missing or non-string turn_id' };
  }
  if (typeof msg.delta !== 'string') {
    return { valid: false, error: 'Missing or non-string delta' };
  }
  return {
    valid: true,
    delta: msg.delta,
    turnId: msg.turn_id,
  };
}

/**
 * Validate incoming agent.done completion message.
 *
 * @param {object} msg - Parsed JSON message.
 * @returns {{ valid: boolean, text?: string, turnId?: string, error?: string }}
 */
export function validateAgentDone(msg) {
  if (!msg || typeof msg !== 'object') {
    return { valid: false, error: 'Message must be an object' };
  }
  if (msg.type !== 'agent.done') {
    return { valid: false, error: `Invalid message type '${msg.type}', expected 'agent.done'` };
  }
  if (typeof msg.turn_id !== 'string' || !msg.turn_id) {
    return { valid: false, error: 'Missing or non-string turn_id' };
  }
  if (typeof msg.text !== 'string') {
    return { valid: false, error: 'Missing or non-string text' };
  }
  return {
    valid: true,
    text: msg.text,
    turnId: msg.turn_id,
  };
}

/**
 * Validate incoming error message.
 *
 * @param {object} msg - Parsed JSON message.
 * @returns {{ valid: boolean, code?: string, message?: string, error?: string }}
 */
export function validateErrorMessage(msg) {
  if (!msg || typeof msg !== 'object') {
    return { valid: false, error: 'Message must be an object' };
  }
  if (msg.type !== 'error') {
    return { valid: false, error: `Invalid message type '${msg.type}', expected 'error'` };
  }
  if (typeof msg.code !== 'string') {
    return { valid: false, error: 'Missing or non-string code' };
  }
  return {
    valid: true,
    code: msg.code,
    message: typeof msg.message === 'string' ? msg.message : '',
  };
}

/**
 * Reply languages of session.start (protocol v0.10, docs/contracts.md §2.3):
 * 'any' lets the reply follow the user's language; 'en' / 'hi' force one.
 */
export const REPLY_LANGUAGES = ['any', 'en', 'hi'];

/**
 * The session.start message. A plain function, outside the hook, so a plain
 * Node test can check exactly what the browser sends.
 *
 * @param {{ persona: string, mode: 'vad'|'ptt', replyLanguage: string,
 *           audio: { sample_rate: number, channels: number, frame_ms: number } }} fields
 * @returns {object} the JSON payload, not yet stringified.
 */
export function buildSessionStart({ persona, mode, replyLanguage, audio }) {
  return { type: 'session.start', persona, mode, reply_language: replyLanguage, audio };
}

/**
 * The reply language the SERVER confirmed in session.started. The server's
 * value wins, as for mode: an older server sends none, and then replies
 * follow the user's language ('any') whatever we asked for.
 *
 * @param {object} msg - a session.started message.
 * @returns {'any'|'en'|'hi'}
 */
export function confirmedReplyLanguage(msg) {
  return REPLY_LANGUAGES.includes(msg?.reply_language) ? msg.reply_language : 'any';
}
