/**
 * StudioHeader -- "File 002 — conversation / Vaani." on the left, the
 * session settings in the middle, and the status lamp on the right.
 *
 * On a phone the settings do not fit, so the header shows the station as a
 * button instead. It opens a <dialog> (a native modal: the browser traps
 * focus inside it, Esc closes it, and the page behind is inert) holding the
 * same settings plus the Ink toggle and Sign out, which live in the rail on
 * desktop.
 */

import { useRef } from 'react';
import { useLoaderData } from 'react-router-dom';
import useSignOut from '../login/useSignOut.js';
import { operatorFor } from '../login/loginState.js';
import StudioSettings from './StudioSettings.jsx';
import { PERSONAS, TEXT } from './talkContent.js';
import { VaaniIcon } from '../components/brand/VaaniLogo.jsx';

export default function StudioHeader({ settings, lamp, lampTone, ink, onToggleInk }) {
  const sheetRef = useRef(null);
  const signOut = useSignOut();
  const { signedIn } = operatorFor(useLoaderData()); // no Sign out when auth is off
  const station = PERSONAS.find((p) => p.id === settings.persona) ?? PERSONAS[0];

  return (
    <header className="tk-header">
      <div className="tk-brand">
        <span className="tk-phone-only tk-brand-mark" aria-hidden="true"><VaaniIcon size={28} ink="var(--tk-text)" paper="var(--tk-bg)" /></span>
        <span className="tk-mono tk-file tk-wide-only">{TEXT.file}</span>
        <h1 className="tk-cd tk-title">{TEXT.title}<span className="tk-dot" aria-hidden="true">.</span></h1>
      </div>

      <div className="tk-wide-only tk-header-settings">
        <StudioSettings {...settings} />
      </div>

      <p className={`tk-mono tk-lamp tk-lamp-${lampTone} tk-wide-only`}>
        <span className="tk-lamp-dot" aria-hidden="true" />
        {lamp}
      </p>

      <button type="button" className="tk-mono tk-pill tk-phone-only"
        aria-haspopup="dialog" aria-label={`${TEXT.settingsButton}: ${station.label}`}
        onClick={() => sheetRef.current?.showModal()}>
        {station.label} <span aria-hidden="true">▾</span>
      </button>

      <dialog ref={sheetRef} className="tk-sheet" aria-label={TEXT.settingsTitle}>
        <h2 className="tk-cd tk-sheet-title">{TEXT.settingsTitle}</h2>
        <StudioSettings {...settings} />
        <button type="button" className="tk-mono tk-pill" onClick={onToggleInk}>
          {ink ? TEXT.rail.paper : TEXT.rail.ink}
        </button>
        {signedIn && <button type="button" className="tk-mono tk-pill" onClick={signOut}>{TEXT.rail.signOut}</button>}
        <button type="button" className="tk-mono tk-pill tk-sheet-close" onClick={() => sheetRef.current?.close()}>
          {TEXT.close}
        </button>
      </dialog>
    </header>
  );
}
