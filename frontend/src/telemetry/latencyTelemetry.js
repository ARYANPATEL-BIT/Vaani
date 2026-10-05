/**
 * latencyTelemetry.js — Contract-driven telemetry stage definitions and parser
 * for the Vaani Latency HUD (Week 3, Day 1).
 *
 * Source of truth:
 * - backend/vaani/telemetry.py (canonical span constants: vad_decision, turn_ended,
 *   asr_final, llm_first_token, tts_first_audio, playback_start).
 * - docs/findings/perf-1-latency-budget.md (measured pipeline stages and targets).
 * - docs/contracts.md (SHARED PROTOCOL v0.5 telemetry specification).
 */

/**
 * Official pipeline stages displayed in the Latency HUD.
 * Ordered by pipeline execution flow: Voice -> VAD -> Endpointer -> ASR -> LLM -> TTS -> Playback.
 */
export const STAGE_DEFINITIONS = [
  {
    key: 'vad',
    label: 'Voice Activity (VAD)',
    shortLabel: 'VAD',
    spanName: 'vad_decision',
    description: 'Time spent in Silero VAD evaluating speech energy per frame.',
  },
  {
    key: 'endpointing',
    label: 'Endpointing Wait',
    shortLabel: 'Endpointer',
    spanName: 'turn_ended',
    description: 'Silence threshold waited to verify end of turn (speech_ended -> turn_ended).',
  },
  {
    key: 'asr',
    label: 'Speech-to-Text (ASR)',
    shortLabel: 'ASR',
    spanName: 'asr_final',
    description: 'Acoustic inference duration producing final transcript (Whisper large-v3).',
  },
  {
    key: 'llm',
    label: 'LLM First Token',
    shortLabel: 'LLM',
    spanName: 'llm_first_token',
    description: 'Prompt assembly and network time to stream the first reply token.',
  },
  {
    key: 'tts',
    label: 'Speech Synthesis (TTS)',
    shortLabel: 'TTS',
    spanName: 'tts_first_audio',
    description: 'Time to synthesize initial audio frames from reply text.',
  },
  {
    key: 'playback',
    label: 'Playback Scheduling',
    shortLabel: 'Playback',
    spanName: 'playback_start',
    description: 'Web Audio queue buffer and scheduling delay to first audible sample.',
  },
];

/**
 * Map of alternative keys/aliases to canonical stage keys.
 * Handles both stage keys ('vad', 'endpointing', etc.) and raw span names
 * from backend/vaani/telemetry.py ('vad_decision', 'turn_ended', etc.).
 */
const STAGE_KEY_ALIASES = {
  vad: 'vad',
  vad_ms: 'vad',
  vad_decision: 'vad',
  endpoint: 'endpointing',
  endpointing: 'endpointing',
  endpointing_ms: 'endpointing',
  turn_ended: 'endpointing',
  endpointer: 'endpointing',
  asr: 'asr',
  asr_ms: 'asr',
  asr_final: 'asr',
  asr_decode: 'asr',
  llm: 'llm',
  llm_ms: 'llm',
  llm_first_token: 'llm',
  first_token: 'llm',
  tts: 'tts',
  tts_ms: 'tts',
  tts_first_audio: 'tts',
  playback: 'playback',
  playback_ms: 'playback',
  playback_start: 'playback',
};

/**
 * Format a numeric latency in milliseconds for display.
 * Returns formatted string with 'ms' suffix, or '—' if value is missing/invalid.
 *
 * @param {number|null|undefined} value - Duration in milliseconds.
 * @returns {string} Formatted latency string (e.g. "280 ms" or "—").
 */
export function formatLatencyMs(value) {
  if (typeof value === 'number' && !Number.isNaN(value) && Number.isFinite(value) && value >= 0) {
    return `${Math.round(value)} ms`;
  }
  return '—';
}

/**
 * Validate and normalize a single stage duration value.
 * Must be a finite non-negative number. Returns null if invalid or undefined.
 *
 * @param {*} val
 * @returns {number|null}
 */
function sanitizeDuration(val) {
  if (typeof val === 'number' && Number.isFinite(val) && !Number.isNaN(val) && val >= 0) {
    return Math.round(val * 10) / 10;
  }
  return null;
}

/**
 * Parse an incoming WebSocket server message as a telemetry payload.
 *
 * Valid message types:
 * - 'telemetry'
 * - 'telemetry.spans'
 * - 'telemetry.turn'
 *
 * Supported stage payload formats:
 * 1. Object map: { stages: { vad: 280, asr: 577, ... } }
 * 2. Array of objects: { stages: [ { name: 'vad', duration_ms: 280 }, ... ] }
 * 3. Flat keys: { vad_ms: 280, asr_ms: 577, ... }
 *
 * Guarantees:
 * - Never invents default or simulated values.
 * - Missing stages evaluate strictly to null.
 * - Safely rejects malformed or unrecognised payloads.
 *
 * @param {*} rawMessage - Parsed JSON object received from WebSocket.
 * @returns {object} Normalized telemetry result:
 *   {
 *     valid: boolean,
 *     turnId: string | null,
 *     stages: { vad: number|null, endpointing: number|null, ... },
 *     totalMs: number | null,
 *     hasData: boolean,
 *     isPartial: boolean,
 *     error?: string,
 *   }
 */
export function parseTelemetryPayload(rawMessage) {
  if (!rawMessage || typeof rawMessage !== 'object' || Array.isArray(rawMessage)) {
    return { valid: false, error: 'Payload must be a non-null JSON object.' };
  }

  const { type } = rawMessage;
  if (type !== 'telemetry' && type !== 'telemetry.spans' && type !== 'telemetry.turn') {
    return { valid: false, error: `Unrecognised message type: ${type}` };
  }

  const turnId = typeof rawMessage.turn_id === 'string' && rawMessage.turn_id.trim()
    ? rawMessage.turn_id.trim()
    : null;

  // Initialize stage map with all official stages as null
  const stages = {
    vad: null,
    endpointing: null,
    asr: null,
    llm: null,
    tts: null,
    playback: null,
  };

  const rawStages = rawMessage.stages;

  // Format 1: Array of stage entries [{ name: 'vad', duration_ms: 280 }, ...]
  if (Array.isArray(rawStages)) {
    for (const item of rawStages) {
      if (item && typeof item === 'object') {
        const rawName = String(item.name || item.stage || item.id || '').toLowerCase().trim();
        const canonicalKey = STAGE_KEY_ALIASES[rawName];
        if (canonicalKey && canonicalKey in stages) {
          const dur = sanitizeDuration(item.duration_ms ?? item.duration ?? item.ms);
          if (dur !== null) {
            stages[canonicalKey] = dur;
          }
        }
      }
    }
  } else if (rawStages && typeof rawStages === 'object') {
    // Format 2: Object dictionary { vad: 280, asr: 577, ... }
    for (const [key, val] of Object.entries(rawStages)) {
      const lowerKey = key.toLowerCase().trim();
      const canonicalKey = STAGE_KEY_ALIASES[lowerKey];
      if (canonicalKey && canonicalKey in stages) {
        const dur = sanitizeDuration(val);
        if (dur !== null) {
          stages[canonicalKey] = dur;
        }
      }
    }
  } else {
    // Format 3: Flat properties on root payload (e.g. rawMessage.vad_ms = 280)
    for (const [key, val] of Object.entries(rawMessage)) {
      const lowerKey = key.toLowerCase().trim();
      const canonicalKey = STAGE_KEY_ALIASES[lowerKey];
      if (canonicalKey && canonicalKey in stages) {
        const dur = sanitizeDuration(val);
        if (dur !== null) {
          stages[canonicalKey] = dur;
        }
      }
    }
  }

  // Calculate or extract total latency
  let totalMs = sanitizeDuration(rawMessage.total_ms ?? rawMessage.total);

  // If total is not provided in payload, compute sum of present stages
  const presentValues = Object.values(stages).filter((v) => v !== null);
  const hasData = presentValues.length > 0;

  if (totalMs === null && hasData) {
    totalMs = Math.round(presentValues.reduce((acc, curr) => acc + curr, 0) * 10) / 10;
  }

  const stageKeys = Object.keys(stages);
  const presentCount = presentValues.length;
  const isPartial = hasData && presentCount < stageKeys.length;

  return {
    valid: true,
    turnId,
    timestamp: Date.now(),
    stages,
    totalMs,
    hasData,
    isPartial,
  };
}
