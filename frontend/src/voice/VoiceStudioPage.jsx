/**
 * VoiceStudioPage (/voice) -- enrol your own voice, then hear a script in it.
 *
 * The route's loader (router.jsx) asks the studio one question before the
 * page is drawn, GET /studio/voice ("is my voice enrolled?"), and the page
 * shows one of two panels:
 *   not enrolled -> EnrolPanel (consent, sample, live challenge);
 *   enrolled     -> GeneratePanel (script to audio, and delete).
 * After an enrolment, a generation or a delete, revalidate() makes the
 * router run the loader again, so the studio's answer is the only state that
 * decides what is shown.
 *
 * Replaces the old /enrol pages, which called /api/enrol/* routes that never
 * existed (docs/learning/backend-learning/25-voice-studio.md).
 */

import { useLoaderData, useRevalidator } from 'react-router-dom';
import EnrolPanel from './EnrolPanel.jsx';
import GeneratePanel from './GeneratePanel.jsx';
import './voiceStudio.css';

export default function VoiceStudioPage() {
  const { body: voice, error } = useLoaderData(); // studioApi's { status, body, error }
  const { revalidate } = useRevalidator();

  return (
    <main className="vs-page" aria-labelledby="vs-title">
      <header>
        <h1 id="vs-title">Voice studio</h1>
        <p className="vs-hint">Your own voice only. Hindi or English. Delete it any time.</p>
      </header>
      {error && <p className="vs-error" role="alert">{error}</p>}
      {voice && !voice.enrolled && <EnrolPanel voice={voice} onEnrolled={revalidate} />}
      {voice && voice.enrolled && <GeneratePanel voice={voice} onChanged={revalidate} />}
    </main>
  );
}
