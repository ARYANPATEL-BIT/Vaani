/* global process */
/**
 * turnFilter.test.js — dropping what arrives for a flushed turn
 * (turnFilter.js, docs/contracts.md §2.3, §2.7, §2.8).
 *
 * Covers:
 * 1. Nothing is dropped before any flush.
 * 2. After audio.flush, that turn's frames and reply messages are dropped,
 *    but turn.state, transcripts and errors pass.
 * 3. A new turn's audio.start lets its frames through again.
 * 4. A local flush (speak pressed over the agent) drops frames already in
 *    flight before the server's audio.flush arrives.
 * 5. A stale audio.start for a flushed turn keeps its frames dropped (the
 *    hole the old single true/false flag had).
 *
 * Run with:
 *   node frontend/src/turnState/turnFilter.test.js
 */

import { createTurnFilter } from './turnFilter.js';

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

console.log('=== Flushed-turn filter ===\n');

console.log('1. Before any flush:');
{
  const filter = createTurnFilter();
  assert('a frame before any audio.start passes', filter.dropFrame() === false);
  assert('audio.start passes', filter.dropMessage({ type: 'audio.start', turn_id: 'a' }) === false);
  assert('its frames pass', filter.dropFrame() === false);
  assert('agent.text passes', filter.dropMessage({ type: 'agent.text', turn_id: 'a', delta: 'x' }) === false);
}

console.log('\n2. After audio.flush for turn a:');
{
  const filter = createTurnFilter();
  filter.dropMessage({ type: 'audio.start', turn_id: 'a' });
  filter.flush('a');
  assert('frames of a are dropped', filter.dropFrame() === true);
  assert('agent.text for a is dropped', filter.dropMessage({ type: 'agent.text', turn_id: 'a', delta: 'x' }) === true);
  assert('agent.done for a is dropped', filter.dropMessage({ type: 'agent.done', turn_id: 'a', text: 'x' }) === true);
  assert('audio.end for a is dropped', filter.dropMessage({ type: 'audio.end', turn_id: 'a' }) === true);
  assert('turn.state for a passes', filter.dropMessage({ type: 'turn.state', turn_id: 'a', state: 'cancelling' }) === false);
  assert('transcript.final for a passes', filter.dropMessage({ type: 'transcript.final', turn_id: 'a', text: 'x' }) === false);
  assert('error passes', filter.dropMessage({ type: 'error', code: 'TTS_FAILED' }) === false);
  assert('audio.flush passes', filter.dropMessage({ type: 'audio.flush', turn_id: 'a' }) === false);
  assert('agent.text for another turn passes', filter.dropMessage({ type: 'agent.text', turn_id: 'b', delta: 'y' }) === false);
}

console.log('\n3. The next turn plays again:');
{
  const filter = createTurnFilter();
  filter.dropMessage({ type: 'audio.start', turn_id: 'a' });
  filter.flush('a');
  assert('audio.start for b passes', filter.dropMessage({ type: 'audio.start', turn_id: 'b' }) === false);
  assert('frames of b pass', filter.dropFrame() === false);
}

console.log('\n4. Local flush before the server answers:');
{
  const filter = createTurnFilter();
  filter.dropMessage({ type: 'audio.start', turn_id: 'a' });
  filter.flush('a'); // speak pressed while a was speaking
  assert('in-flight frames of a are dropped', filter.dropFrame() === true);
  filter.flush('a'); // the server's audio.flush arrives later
  assert('a second flush of a changes nothing', filter.dropFrame() === true);
  filter.flush(null); // speak pressed while idle: no turn to flush
  assert('flush(null) is ignored', filter.dropFrame() === true);
}

console.log('\n5. Stale audio.start for a flushed turn:');
{
  const filter = createTurnFilter();
  filter.flush('a'); // cut while thinking: no audio.start came first
  assert('audio.start for a is dropped', filter.dropMessage({ type: 'audio.start', turn_id: 'a' }) === true);
  assert('frames after it are dropped', filter.dropFrame() === true);
}

console.log(`\n--- Results: ${passed} passed, ${failed} failed ---`);

if (failed > 0) {
  process.exit(1);
}
