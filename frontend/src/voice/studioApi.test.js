/* global process */
/**
 * studioApi.test.js -- the voice studio calls (api/studioApi.js) on the REAL
 * module with a fake fetch, plus the microphone constraints. No server.
 *
 * Covers: paths and methods; the enrol form's three fields; the studio's own
 * refusal message passed through unchanged; "studio not running" when no
 * answer comes or Vite's proxy answers without JSON; generate handing back the
 * WAV blob and its id; an aborted generate is not reported as an error; and
 * AGC, noise suppression and echo cancellation all off.
 *
 * Run with:
 *   node frontend/src/voice/studioApi.test.js
 */

import {
  STUDIO_DOWN, deleteVoice, enrol, fetchVoice, generate, newChallenge,
} from '../api/studioApi.js';
import { MIC_CONSTRAINTS } from './useMicRecorder.js';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${description}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${description}`);
  }
}

/** A fake fetch that records its calls and answers with `status` and `body`. */
function fakeFetch(status, body, { blob, headers = {} } = {}) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url, options });
    return {
      status,
      ok: status >= 200 && status < 300,
      json: async () => {
        if (body === undefined) throw new SyntaxError('no JSON body');
        return body;
      },
      blob: async () => blob,
      headers: { get: (name) => headers[name] ?? null },
    };
  };
  fn.calls = calls;
  return fn;
}

const throwing = (name) => async () => {
  const err = new Error(name);
  err.name = name;
  throw err;
};

console.log('studioApi: paths and methods');
{
  const f = fakeFetch(200, { enrolled: false });
  const res = await fetchVoice({ fetchFn: f });
  assert('GET /studio/voice', f.calls[0].url === '/studio/voice' && f.calls[0].options.method === 'GET');
  assert('body handed back, no error', res.body.enrolled === false && res.error === null);

  const c = fakeFetch(200, { phrase: 'river tiger' });
  await newChallenge({ fetchFn: c });
  assert('POST /studio/challenge', c.calls[0].url === '/studio/challenge' && c.calls[0].options.method === 'POST');

  const d = fakeFetch(200, { deleted: true });
  await deleteVoice({ fetchFn: d });
  assert('DELETE /studio/voice', d.calls[0].options.method === 'DELETE');
}

console.log('studioApi: enrol form');
{
  const f = fakeFetch(200, { enrolled: true });
  await enrol(
    { sample: new Blob(['a']), sampleName: 'phone.m4a', challenge: new Blob(['b']), consentText: 'I agree' },
    { fetchFn: f },
  );
  const form = f.calls[0].options.body;
  assert('posts to /studio/enrol', f.calls[0].url === '/studio/enrol');
  assert('sample keeps the uploaded name', form.get('sample').name === 'phone.m4a');
  assert('challenge field present', form.get('challenge') instanceof Blob);
  assert('consent text sent as is', form.get('consent_text') === 'I agree');
}

console.log('studioApi: errors');
{
  const refusal = { type: 'error', code: 'STUDIO_LOW_SNR', message: 'Too noisy: move to a quiet room.' };
  const res = await enrol(
    { sample: new Blob(['a']), sampleName: 's.webm', challenge: new Blob(['b']), consentText: 'x' },
    { fetchFn: fakeFetch(422, refusal) },
  );
  assert("the studio's own message is shown", res.error === refusal.message);
  assert('the code is still readable', res.body.code === 'STUDIO_LOW_SNR');

  const down = await fetchVoice({ fetchFn: throwing('TypeError') });
  assert('no answer -> studio not running', down.status === null && down.error === STUDIO_DOWN);

  const proxy = await fetchVoice({ fetchFn: fakeFetch(502, undefined) });
  assert("proxy's non-JSON 502 -> studio not running", proxy.error === STUDIO_DOWN);

  const html = await fetchVoice({ fetchFn: fakeFetch(200, undefined) });
  assert('a 200 HTML page (no studio deployed) -> studio not running', html.error === STUDIO_DOWN);
}

console.log('studioApi: generate');
{
  const wav = new Blob(['RIFF'], { type: 'audio/wav' });
  const f = fakeFetch(200, undefined, { blob: wav, headers: { 'X-Generation-Id': 'abc123' } });
  const signal = new AbortController().signal;
  const res = await generate('Hello.', { signal, fetchFn: f });
  assert('JSON body with the script', JSON.parse(f.calls[0].options.body).script === 'Hello.');
  assert('the abort signal reaches fetch', f.calls[0].options.signal === signal);
  assert('blob and id handed back', res.body.blob === wav && res.body.generationId === 'abc123');

  const busy = await generate('Hi.', { fetchFn: fakeFetch(503, { code: 'STUDIO_GPU_BUSY', message: 'GPU full.' }) });
  assert('GPU busy message shown', busy.error === 'GPU full.');

  const aborted = await generate('Hi.', { fetchFn: throwing('AbortError') });
  assert('a cancel is not an error', aborted.error === null && aborted.status === null);
}

console.log('useMicRecorder: constraints');
{
  const a = MIC_CONSTRAINTS.audio;
  assert('autoGainControl off', a.autoGainControl === false);
  assert('noiseSuppression off', a.noiseSuppression === false);
  assert('echoCancellation off', a.echoCancellation === false);
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
