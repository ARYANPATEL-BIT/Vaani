/**
 * verifyDemo.js — fake server answers for /enrol/verify?demo=..., so the
 * screen can be seen without a backend (like ?reason= on the validation page).
 *
 *   ?demo=ok             sample loads, approval succeeds
 *   ?demo=load-error     the render call fails
 *   ?demo=approve-error  sample loads, the approval call fails
 *
 * The "sample" is a 1.5 s 440 Hz tone, not a voice. The page labels demo
 * mode on screen so nobody mistakes it for a real approval.
 */

const DEMO_DELAY_MS = 800; // long enough to see the loading / approving states

export const DEMO_MODES = ['ok', 'load-error', 'approve-error'];

function wait(ms, signal) {
  return new Promise((resolve) => {
    const id = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => { clearTimeout(id); resolve(); }, { once: true });
  });
}

/** Same result shape as renderVerificationSample in api/enrolApi.js. */
export async function demoRender(mode, { signal } = {}) {
  await wait(DEMO_DELAY_MS, signal);
  if (mode === 'load-error') {
    return { ok: false, error: 'Demo: the server could not render the test sentence.' };
  }
  return { ok: true, audioBlob: makeToneWav() };
}

/** Same result shape as approveVoice in api/enrolApi.js. */
export async function demoApprove(mode, { signal } = {}) {
  await wait(DEMO_DELAY_MS, signal);
  if (mode === 'approve-error') {
    return { ok: false, error: 'Demo: the server did not confirm the approval.' };
  }
  return { ok: true };
}

/**
 * Build a WAV file in memory: a 44-byte header that describes the audio
 * (16-bit mono PCM), followed by the samples of a sine wave.
 */
function makeToneWav(seconds = 1.5, freqHz = 440, sampleRate = 16000) {
  const n = Math.floor(seconds * sampleRate);
  const view = new DataView(new ArrayBuffer(44 + n * 2));
  const text = (offset, s) => [...s].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));

  text(0, 'RIFF'); view.setUint32(4, 36 + n * 2, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);           // mono
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, n * 2, true);

  for (let i = 0; i < n; i++) {
    const sample = Math.sin((2 * Math.PI * freqHz * i) / sampleRate) * 0.3;
    view.setInt16(44 + i * 2, sample * 0x7fff, true);
  }
  return new Blob([view], { type: 'audio/wav' });
}
