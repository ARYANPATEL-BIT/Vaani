/**
 * EnrolPanel -- the three steps of enrolling your own voice (ETH-1, 2, 3).
 *
 *   1. Consent: the studio's consent text, word for word, and a checkbox.
 *      The text is only sent when the box is ticked, and the studio stores
 *      exactly that text with a timestamp.
 *   2. Voice sample: 10 to 30 s, recorded here or uploaded (a phone file).
 *   3. Challenge: the studio issues random words; you read them aloud here,
 *      live. The studio checks the words AND that it is the sample's voice.
 *
 * All checks run on the server, in one request; this panel only collects the
 * three inputs and shows the studio's answer, which says how to fix a refusal.
 */

import { useEffect, useMemo, useState } from 'react';
import { enrol, newChallenge } from '../api/studioApi.js';
import { useMicRecorder } from './useMicRecorder.js';

export default function EnrolPanel({ voice, onEnrolled }) {
  const { consent_text: consentText, limits } = voice;
  const [agreed, setAgreed] = useState(false);
  const [upload, setUpload] = useState(null); // a File the user picked
  const [phrase, setPhrase] = useState(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  // Auto-stop 1 s before the studio's limit: the timer ticks every 200 ms
  // and the encoder adds a little, so stopping AT the limit would make a
  // take just over it, which the studio refuses.
  const sampleMic = useMicRecorder(limits.sample_max_s - 1);
  const phraseMic = useMicRecorder(limits.challenge_max_s - 1);

  const sample = upload ?? sampleMic.blob;
  const ready = agreed && sample && phraseMic.blob && phrase && !sending;

  async function getPhrase() {
    setError(null);
    phraseMic.reset();
    const res = await newChallenge();
    if (res.error) setError(res.error);
    else setPhrase(res.body.phrase);
  }

  async function submit() {
    setSending(true);
    setError(null);
    const res = await enrol({
      sample,
      sampleName: upload ? upload.name : 'sample.webm',
      challenge: phraseMic.blob,
      consentText,
    });
    setSending(false);
    if (!res.error) {
      onEnrolled();
      return;
    }
    setError(res.error);
    // The phrase is spent or expired: the next try needs a new one.
    if (res.body?.code === 'STUDIO_NO_CHALLENGE') setPhrase(null);
  }

  return (
    <section className="vs-card" aria-labelledby="vs-enrol-title">
      <h2 id="vs-enrol-title">Enrol your own voice</h2>

      <h3>1. Consent</h3>
      <blockquote className="vs-consent">{consentText}</blockquote>
      <label className="vs-check">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        I agree. This is my own voice.
      </label>

      <h3>2. Voice sample ({limits.sample_min_s}-{limits.sample_max_s} s)</h3>
      <p className="vs-hint">
        Read anything aloud in a quiet room, a hand-width from the mic. Or upload a recording of yourself.
      </p>
      <Recorder mic={sampleMic} minSeconds={limits.sample_min_s} disabled={Boolean(upload)} />
      <label className="vs-upload">
        Or upload a file:{' '}
        <input
          type="file"
          accept="audio/*"
          onChange={(e) => { setUpload(e.target.files[0] ?? null); sampleMic.reset(); }}
        />
      </label>

      <h3>3. Live challenge</h3>
      {phrase ? (
        <>
          <p className="vs-hint">Press record, then read these words aloud:</p>
          <p className="vs-phrase" aria-live="polite">{phrase}</p>
          <Recorder mic={phraseMic} minSeconds={1} />
          <button type="button" className="vs-link" onClick={getPhrase}>New phrase</button>
        </>
      ) : (
        <button type="button" className="vs-btn" onClick={getPhrase}>Show my phrase</button>
      )}

      {error && <p className="vs-error" role="alert">{error}</p>}
      <button type="button" className="vs-btn vs-primary" disabled={!ready} onClick={submit}>
        {sending ? 'Checking...' : 'Enrol my voice'}
      </button>
    </section>
  );
}

/** Record / stop, a timer, and a preview of the finished take. */
function Recorder({ mic, minSeconds, disabled = false }) {
  // An object URL is a short "blob:" address for bytes held in memory, so
  // <audio> can play the take. Each new take gets one; the effect frees the
  // previous one, or the bytes would stay in memory until the tab closes.
  const url = useMemo(() => (mic.blob ? URL.createObjectURL(mic.blob) : null), [mic.blob]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const tooShort = mic.state === 'done' && mic.seconds < minSeconds;
  return (
    <div className="vs-recorder">
      {mic.state === 'recording' ? (
        <button type="button" className="vs-btn vs-stop" onClick={mic.stop}>
          Stop ({mic.seconds.toFixed(0)} s)
        </button>
      ) : (
        <button type="button" className="vs-btn" onClick={mic.start} disabled={disabled}>
          {mic.blob ? 'Record again' : 'Record'}
        </button>
      )}
      {url && <audio controls src={url} />}
      {tooShort && <span className="vs-error">Too short: at least {minSeconds} s.</span>}
      {mic.error && <span className="vs-error">{mic.error}</span>}
    </div>
  );
}
