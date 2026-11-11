/* global process */
/**
 * sessionStart.test.js — what the browser sends in session.start and reads
 * back from session.started (turnContracts.js, docs/contracts.md §2.3).
 *
 * Covers:
 * 1. The chosen reply language ('any', 'en', 'hi') is sent as
 *    reply_language, next to the persona, mode and audio format, unchanged.
 * 2. The reply language shown while connected is the server's echo; a
 *    missing or unknown echo (an older server) reads as 'any'.
 *
 * Not covered: that ConversationPage passes its picker's choice into
 * startCapture, and startCapture into buildSessionStart. There is no React
 * test setup; that wiring is checked by reading the code.
 *
 * Run with:
 *   node frontend/src/turnState/sessionStart.test.js
 */

import {
  REPLY_LANGUAGES,
  buildSessionStart,
  confirmedReplyLanguage,
} from './turnContracts.js';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${description}`);
  } else {
    failed += 1;
    console.error(`  FAIL ${description}`);
  }
}

const AUDIO = { sample_rate: 16000, channels: 1, frame_ms: 20 };

console.log('1. session.start carries the chosen reply language');
for (const replyLanguage of REPLY_LANGUAGES) {
  const sent = JSON.parse(
    JSON.stringify(
      buildSessionStart({ persona: 'tutor', mode: 'ptt', replyLanguage, audio: AUDIO }),
    ),
  );
  assert(`reply_language is '${replyLanguage}'`, sent.reply_language === replyLanguage);
  assert(
    `the rest is unchanged for '${replyLanguage}'`,
    sent.type === 'session.start' &&
      sent.persona === 'tutor' &&
      sent.mode === 'ptt' &&
      JSON.stringify(sent.audio) === JSON.stringify(AUDIO),
  );
}

console.log('2. the server\'s echo is what is shown');
for (const echoed of REPLY_LANGUAGES) {
  assert(
    `echo '${echoed}' is shown as '${echoed}'`,
    confirmedReplyLanguage({ type: 'session.started', reply_language: echoed }) === echoed,
  );
}
assert(
  'no echo (an older server) reads as any',
  confirmedReplyLanguage({ type: 'session.started', session_id: 'x' }) === 'any',
);
assert(
  'an unknown echo reads as any',
  confirmedReplyLanguage({ type: 'session.started', reply_language: 'fr' }) === 'any',
);

console.log(`\n--- Results: ${passed} passed, ${failed} failed ---`);

if (failed > 0) {
  process.exit(1);
}
