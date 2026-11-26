/**
 * GeneratePanel -- type a script, hear it in your enrolled voice, download it;
 * and the one-button delete of that voice (ETH-4).
 *
 * Generating can take tens of seconds (one sentence at a time on the GPU), so
 * it can be cancelled. Cancel aborts the fetch through an AbortController; the
 * studio sees the request close and stops before its next sentence. Leaving
 * the page cancels the same way.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { deleteVoice, generate } from '../api/studioApi.js';

export default function GeneratePanel({ voice, onChanged }) {
  const { limits, enrolled_at: enrolledAt } = voice;
  const [script, setScript] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // { blob, generationId }
  const abortRef = useRef(null);

  // The file to play and download; freed when replaced or on leaving.
  const url = useMemo(() => (result ? URL.createObjectURL(result.blob) : null), [result]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  useEffect(() => () => abortRef.current?.abort(), []);

  async function run() {
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    const res = await generate(script, { signal: controller.signal });
    setBusy(false);
    if (controller.signal.aborted) return; // the user's own cancel
    if (res.error) {
      setError(res.error);
      return;
    }
    setResult(res.body);
    onChanged(); // the "left today" count moved
  }

  async function remove() {
    const sure = window.confirm(
      'Delete your voice? This removes your voice sample, its speaker embedding, ' +
      'your consent record and every file generated from it. It cannot be undone.',
    );
    if (!sure) return;
    const res = await deleteVoice();
    if (res.error) setError(res.error);
    else onChanged();
  }

  const tooLong = script.length > limits.max_script_chars;
  return (
    <>
      <section className="vs-card" aria-labelledby="vs-gen-title">
        <h2 id="vs-gen-title">Generate</h2>
        <p className="vs-hint">
          Hindi sentences (any Devanagari) are spoken as Hindi, the rest as English.
          {' '}{limits.generations_left_today} generations left today.
        </p>
        <textarea
          className="vs-script"
          rows={6}
          value={script}
          onChange={(e) => setScript(e.target.value)}
          placeholder="Type your script here."
          aria-label="Script"
        />
        <p className={tooLong ? 'vs-error' : 'vs-hint'}>
          {script.length} / {limits.max_script_chars} characters
        </p>
        {busy ? (
          <button type="button" className="vs-btn vs-stop" onClick={() => abortRef.current?.abort()}>
            Generating... Cancel
          </button>
        ) : (
          <button
            type="button"
            className="vs-btn vs-primary"
            onClick={run}
            disabled={!script.trim() || tooLong}
          >
            Generate
          </button>
        )}
        {error && <p className="vs-error" role="alert">{error}</p>}
        {url && (
          <div className="vs-result">
            <audio controls src={url} />
            <a className="vs-btn" href={url} download={`vaani-${result.generationId}.wav`}>
              Download WAV
            </a>
            <p className="vs-hint">AI-generated: the file carries a watermark and a provenance note.</p>
          </div>
        )}
      </section>

      <section className="vs-card vs-danger" aria-labelledby="vs-del-title">
        <h2 id="vs-del-title">Your voice</h2>
        <p className="vs-hint">Enrolled {new Date(enrolledAt).toLocaleString()}.</p>
        <button type="button" className="vs-btn vs-delete" onClick={remove} disabled={busy}>
          Delete my voice
        </button>
      </section>
    </>
  );
}
