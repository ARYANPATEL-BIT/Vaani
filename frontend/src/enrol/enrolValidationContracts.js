/**
 * enrolValidationContracts.js — Shared contract definitions, validation reason codes,
 * and user-facing feedback messages for voice enrolment validation.
 *
 * Source:
 * - docs/complete documentation vaani.pdf (DATA-1, DATA-2, SEC-4, TEST-007, Error Handling p. 22 & 25)
 * - docs/contracts.md §3 (Voice enrolment API)
 * - Vaani_4_Week_Build_Plan.docx (Week 3 Day 5: Enrolment validation feedback)
 *
 * Requirements:
 * - Specific user-facing message for each supported validation rejection reason code:
 *   too short, too long, too quiet, clipped, excessive silence, insufficient speech,
 *   low SNR / noise, format mismatch, missing consent, challenge mismatch.
 * - Resilient payload parsing: handles standard API error objects, WebSocket error frames,
 *   string codes, and malformed inputs safely without throwing.
 */

/**
 * Canonical rejection reason codes for voice enrolment audio.
 */
export const REJECTION_REASONS = {
  TOO_SHORT: 'TOO_SHORT',
  TOO_LONG: 'TOO_LONG',
  TOO_QUIET: 'TOO_QUIET',
  CLIPPING: 'CLIPPING',
  EXCESSIVE_SILENCE: 'EXCESSIVE_SILENCE',
  INSUFFICIENT_SPEECH: 'INSUFFICIENT_SPEECH',
  LOW_SNR: 'LOW_SNR',
  UNSUPPORTED_FORMAT: 'UNSUPPORTED_FORMAT',
  CONSENT_MISSING: 'CONSENT_MISSING',
  CHALLENGE_MISMATCH: 'CHALLENGE_MISMATCH',
  UNKNOWN: 'UNKNOWN_REJECTION_REASON',
};

/**
 * Alias mapping to normalize backend codes, domain-prefixed codes (VOICE_*),
 * and legacy codes to canonical reasons.
 */
const REASON_ALIASES = {
  // Duration bounds (DATA-2: 30–60 s)
  TOO_SHORT: REJECTION_REASONS.TOO_SHORT,
  VOICE_TOO_SHORT: REJECTION_REASONS.TOO_SHORT,
  DURATION_TOO_SHORT: REJECTION_REASONS.TOO_SHORT,
  AUDIO_TOO_SHORT: REJECTION_REASONS.TOO_SHORT,

  TOO_LONG: REJECTION_REASONS.TOO_LONG,
  VOICE_TOO_LONG: REJECTION_REASONS.TOO_LONG,
  DURATION_TOO_LONG: REJECTION_REASONS.TOO_LONG,
  AUDIO_TOO_LONG: REJECTION_REASONS.TOO_LONG,

  // Audio level / amplitude
  TOO_QUIET: REJECTION_REASONS.TOO_QUIET,
  VOICE_TOO_QUIET: REJECTION_REASONS.TOO_QUIET,
  LOW_VOLUME: REJECTION_REASONS.TOO_QUIET,
  AUDIO_TOO_QUIET: REJECTION_REASONS.TOO_QUIET,

  // Distortion / clipping
  CLIPPING: REJECTION_REASONS.CLIPPING,
  VOICE_CLIPPING: REJECTION_REASONS.CLIPPING,
  AUDIO_CLIPPING: REJECTION_REASONS.CLIPPING,
  DISTORTED: REJECTION_REASONS.CLIPPING,

  // Silence distribution
  EXCESSIVE_SILENCE: REJECTION_REASONS.EXCESSIVE_SILENCE,
  VOICE_EXCESSIVE_SILENCE: REJECTION_REASONS.EXCESSIVE_SILENCE,
  LONG_SILENCE: REJECTION_REASONS.EXCESSIVE_SILENCE,
  TOO_MUCH_SILENCE: REJECTION_REASONS.EXCESSIVE_SILENCE,

  // Speech presence (DATA-2)
  INSUFFICIENT_SPEECH: REJECTION_REASONS.INSUFFICIENT_SPEECH,
  VOICE_NO_SPEECH: REJECTION_REASONS.INSUFFICIENT_SPEECH,
  NO_SPEECH_DETECTED: REJECTION_REASONS.INSUFFICIENT_SPEECH,
  SPEECH_NOT_DETECTED: REJECTION_REASONS.INSUFFICIENT_SPEECH,

  // Signal-to-noise floor (DATA-2)
  LOW_SNR: REJECTION_REASONS.LOW_SNR,
  VOICE_LOW_SNR: REJECTION_REASONS.LOW_SNR,
  NOISY_BACKGROUND: REJECTION_REASONS.LOW_SNR,
  HIGH_NOISE: REJECTION_REASONS.LOW_SNR,

  // Audio format (DATA-1: 16 kHz mono 16-bit PCM)
  UNSUPPORTED_FORMAT: REJECTION_REASONS.UNSUPPORTED_FORMAT,
  VOICE_UNSUPPORTED_FORMAT: REJECTION_REASONS.UNSUPPORTED_FORMAT,
  BAD_FORMAT: REJECTION_REASONS.UNSUPPORTED_FORMAT,

  // Legal / compliance (TEST-007)
  CONSENT_MISSING: REJECTION_REASONS.CONSENT_MISSING,
  VOICE_CONSENT_MISSING: REJECTION_REASONS.CONSENT_MISSING,
  CONSENT_REQUIRED: REJECTION_REASONS.CONSENT_MISSING,

  // Biometric similarity verification
  CHALLENGE_MISMATCH: REJECTION_REASONS.CHALLENGE_MISMATCH,
  VOICE_CHALLENGE_MISMATCH: REJECTION_REASONS.CHALLENGE_MISMATCH,
  SPEAKER_MISMATCH: REJECTION_REASONS.CHALLENGE_MISMATCH,
  LOW_SIMILARITY: REJECTION_REASONS.CHALLENGE_MISMATCH,
};

/**
 * Detailed specification for every supported validation rejection reason.
 * Each entry provides a distinct title, specific explanation, remedy, category,
 * and technical contract reference.
 */
export const REJECTION_FEEDBACK_DETAILS = {
  [REJECTION_REASONS.TOO_SHORT]: {
    code: REJECTION_REASONS.TOO_SHORT,
    title: 'Recording Too Short',
    category: 'duration',
    specReference: 'DATA-2 (Duration ≥ 30 s)',
    message:
      'The audio is shorter than the 30-second minimum requirement. At least 30 seconds of speech is needed to train a high-fidelity voice profile.',
    remedy:
      'Please record again and speak continuously for at least 30 seconds before stopping.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.TOO_LONG]: {
    code: REJECTION_REASONS.TOO_LONG,
    title: 'Recording Exceeds Maximum Duration',
    category: 'duration',
    specReference: 'DATA-2 (Duration ≤ 60 s)',
    message:
      'The recording exceeds the 60-second limit. Enrolment reference audio must remain between 30 and 60 seconds.',
    remedy:
      'Keep your recording under 60 seconds. The recorder will automatically finish at the 60-second mark.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.TOO_QUIET]: {
    code: REJECTION_REASONS.TOO_QUIET,
    title: 'Microphone Audio Too Quiet',
    category: 'audio_quality',
    specReference: 'DATA-2 (Signal Floor)',
    message:
      'The recorded volume level is too low. The audio signal does not meet the minimum signal-to-noise floor needed for acoustic feature extraction.',
    remedy:
      'Move closer to your microphone, raise your microphone input volume in system settings, and speak in a clear, natural voice.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.CLIPPING]: {
    code: REJECTION_REASONS.CLIPPING,
    title: 'Audio Distortion (Clipping) Detected',
    category: 'audio_quality',
    specReference: 'DATA-1 (16-bit PCM Linear Range)',
    message:
      'Audio distortion or waveform clipping was detected. The microphone input peaked beyond the maximum dynamic range, which ruins voice synthesis quality.',
    remedy:
      'Lower your microphone input gain or move slightly back from your microphone to avoid over-driving the input.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.EXCESSIVE_SILENCE]: {
    code: REJECTION_REASONS.EXCESSIVE_SILENCE,
    title: 'Excessive Silence in Recording',
    category: 'speech',
    specReference: 'DATA-2 (Continuous Speech)',
    message:
      'Too much silence or long pauses were detected throughout the recording. Voice enrolment requires sustained natural speech rather than empty pauses.',
    remedy:
      'Try reading a continuous article, news excerpt, or story aloud without pausing for more than 2 seconds at a time.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.INSUFFICIENT_SPEECH]: {
    code: REJECTION_REASONS.INSUFFICIENT_SPEECH,
    title: 'Insufficient Speech Detected',
    category: 'speech',
    specReference: 'DATA-2 (Speech Presence)',
    message:
      'No clear vocal speech was detected in the recording. Non-vocal sounds, room tone, or breathing cannot be used to clone a voice.',
    remedy:
      'Ensure your microphone is capturing your voice clearly and speak audibly throughout the 30–60 second recording.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.LOW_SNR]: {
    code: REJECTION_REASONS.LOW_SNR,
    title: 'Background Noise Too High',
    category: 'audio_quality',
    specReference: 'DATA-2 (Signal-to-Noise Floor)',
    message:
      'The signal-to-noise ratio (SNR) is too low. Excessive background hiss, ambient chatter, fan noise, or room echo degrades voice profile generation.',
    remedy:
      'Move to a quieter environment, close nearby windows, turn off noisy fans or air conditioning, and use a headset microphone if possible.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.UNSUPPORTED_FORMAT]: {
    code: REJECTION_REASONS.UNSUPPORTED_FORMAT,
    title: 'Unsupported Audio Format',
    category: 'format',
    specReference: 'DATA-1 (16 kHz, Mono, 16-bit PCM)',
    message:
      'The recorded audio format is incompatible with the enrolment ingest engine. Audio must be mono 16 kHz 16-bit PCM.',
    remedy:
      'Ensure your browser supports Web Audio capture and has not overridden the microphone sampling rate.',
    action: 'rerecord',
  },

  [REJECTION_REASONS.CONSENT_MISSING]: {
    code: REJECTION_REASONS.CONSENT_MISSING,
    title: 'Spoken Consent Missing',
    category: 'compliance',
    specReference: 'TEST-007 (Mandatory Spoken Consent)',
    message:
      'Enrolment blocked: A verified spoken consent statement and live challenge phrase must be recorded before reference audio can be processed.',
    remedy:
      'Return to the consent screen and complete both the spoken consent statement and the live challenge phrase.',
    action: 'consent',
  },

  [REJECTION_REASONS.CHALLENGE_MISMATCH]: {
    code: REJECTION_REASONS.CHALLENGE_MISMATCH,
    title: 'Voice Identity Verification Failed',
    category: 'compliance',
    specReference: 'PERF-9 (Cosine Similarity ≥ 0.80)',
    message:
      'The voice in the reference recording does not match the voice from the live challenge phrase. The speaker similarity score fell below the required threshold.',
    remedy:
      'Ensure the same person speaks both the live challenge phrase and the reference voice recording.',
    action: 'consent',
  },

  [REJECTION_REASONS.UNKNOWN]: {
    code: REJECTION_REASONS.UNKNOWN,
    title: 'Validation Check Failed',
    category: 'general',
    specReference: 'General Enrolment Validation',
    message:
      'The recording could not be validated by the system. Please check your audio setup and review the recording guidelines.',
    remedy:
      'Please re-record your reference voice in a quiet room, speaking clearly for 30–60 seconds.',
    action: 'rerecord',
  },
};

/**
 * Safely parse and normalize an incoming validation rejection payload.
 *
 * Handles:
 * - Direct reason code string: "TOO_SHORT", "VOICE_TOO_QUIET"
 * - API error body: { error: { code: "VOICE_CLIPPING", message: "..." } }
 * - Direct rejection object: { valid: false, reason: "CLIPPING", message: "..." }
 * - WebSocket error frame: { type: "error", code: "VOICE_TOO_SHORT", message: "..." }
 * - Unknown or malformed objects without crashing.
 *
 * @param {any} input - Raw rejection payload or code.
 * @returns {{
 *   valid: boolean,
 *   rawCode: string,
 *   canonicalCode: string,
 *   title: string,
 *   message: string,
 *   remedy: string,
 *   category: string,
 *   specReference: string,
 *   action: string,
 *   serverMessage?: string,
 *   isKnownReason: boolean
 * }}
 */
export function parseValidationFeedback(input) {
  if (!input) {
    const unknown = REJECTION_FEEDBACK_DETAILS[REJECTION_REASONS.UNKNOWN];
    return {
      valid: false,
      rawCode: 'UNKNOWN',
      canonicalCode: unknown.code,
      title: unknown.title,
      message: unknown.message,
      remedy: unknown.remedy,
      category: unknown.category,
      specReference: unknown.specReference,
      action: unknown.action,
      isKnownReason: false,
    };
  }

  let extractedCode = '';
  let serverMessage = '';

  if (typeof input === 'string') {
    extractedCode = input.trim();
  } else if (typeof input === 'object') {
    // Check nested error object: { error: { code: '...', message: '...' } }
    if (input.error && typeof input.error === 'object') {
      extractedCode = input.error.code || input.error.reason || '';
      serverMessage = input.error.message || '';
    } else {
      // Check top-level properties: code, reason, rejection_reason, detail
      extractedCode =
        input.code ||
        input.reason ||
        input.rejection_reason ||
        input.rejectionReason ||
        input.detail ||
        '';
      serverMessage = input.message || '';
    }
  }

  const normalizedCodeKey = String(extractedCode).toUpperCase().trim();
  const canonicalCode = REASON_ALIASES[normalizedCodeKey] || REJECTION_REASONS.UNKNOWN;
  const isKnownReason = canonicalCode !== REJECTION_REASONS.UNKNOWN;

  const detail = REJECTION_FEEDBACK_DETAILS[canonicalCode];

  return {
    valid: false,
    rawCode: extractedCode || 'UNKNOWN',
    canonicalCode,
    title: detail.title,
    message: detail.message,
    remedy: detail.remedy,
    category: detail.category,
    specReference: detail.specReference,
    action: detail.action,
    serverMessage: serverMessage && typeof serverMessage === 'string' ? serverMessage.trim() : undefined,
    isKnownReason,
  };
}

/**
 * Client-side pre-validation for reference voice recording.
 * Checks durations and signal levels before upload/submission according to DATA-2.
 *
 * @param {{ durationSeconds: number, avgLevel?: number, isConsentConfirmed?: boolean }} params
 * @returns {{ valid: boolean, error?: ReturnType<typeof parseValidationFeedback> }}
 */
export function clientPreValidateRecording({
  durationSeconds,
  avgLevel = 0.5,
  isConsentConfirmed = true,
}) {
  if (!isConsentConfirmed) {
    return {
      valid: false,
      error: parseValidationFeedback(REJECTION_REASONS.CONSENT_MISSING),
    };
  }

  if (typeof durationSeconds !== 'number' || durationSeconds < 30) {
    return {
      valid: false,
      error: parseValidationFeedback(REJECTION_REASONS.TOO_SHORT),
    };
  }

  if (durationSeconds > 60) {
    return {
      valid: false,
      error: parseValidationFeedback(REJECTION_REASONS.TOO_LONG),
    };
  }

  if (typeof avgLevel === 'number' && avgLevel < 0.03) {
    return {
      valid: false,
      error: parseValidationFeedback(REJECTION_REASONS.TOO_QUIET),
    };
  }

  return { valid: true };
}
