/**
 * StudioSettings -- the three session choices: station (persona), reply
 * language and input mode. Shown in the header on desktop, and inside the
 * settings sheet on a phone (StudioHeader.jsx). All three are fixed once a
 * session starts, exactly as before: the buttons are disabled while
 * capturing, and the language shows what the server confirmed.
 */

import { MODES, PERSONAS, REPLY_LANGUAGES, TEXT } from './talkContent.js';

export default function StudioSettings({ persona, onPersona, language, onLanguage, mode, onMode, locked }) {
  const station = PERSONAS.find((p) => p.id === persona) ?? PERSONAS[0];
  const modeLabel = MODES.find((m) => m.id === mode)?.label;

  return (
    <div className="tk-settings">
      {/* The radio dial: ticks, a red needle on the chosen station, and the
          stations as real buttons placed along it. */}
      <div className="tk-dial" role="group" aria-label={TEXT.station}>
        <span className="tk-dial-ticks" aria-hidden="true" />
        <span className="tk-dial-needle" aria-hidden="true" style={{ left: `${station.dialPct}%` }} />
        {PERSONAS.map((p) => (
          <button key={p.id} type="button" className="tk-mono tk-station"
            style={{ left: `${p.dialPct}%` }}
            aria-pressed={p.id === persona}
            disabled={locked}
            title={locked ? TEXT.lockedHint : p.desc}
            onClick={() => onPersona(p.id)}>
            {p.label}
          </button>
        ))}
        <span className="tk-mono tk-dial-label" aria-hidden="true">{TEXT.station}</span>
      </div>

      <div className="tk-seg" role="group" aria-label={TEXT.replyGroup}>
        {REPLY_LANGUAGES.map((r) => (
          <button key={r.id} type="button"
            className={r.devanagari ? 'tk-dv tk-seg-btn' : 'tk-mono tk-seg-btn'}
            aria-pressed={r.id === language}
            aria-label={r.name}
            disabled={locked}
            title={locked ? TEXT.lockedHint : r.name}
            onClick={() => onLanguage(r.id)}>
            {r.label}
          </button>
        ))}
      </div>

      {/* A switch: on = push-to-talk. Its name is the visible text, so
          voice-control users can say what they see. */}
      <button type="button" role="switch" className="tk-mono tk-switch"
        aria-checked={mode === 'ptt'}
        disabled={locked}
        title={locked ? TEXT.lockedHint : modeLabel}
        onClick={() => onMode(mode === 'ptt' ? 'vad' : 'ptt')}>
        {TEXT.modeSwitch}
        <span className="tk-switch-track" aria-hidden="true"><span className="tk-switch-knob" /></span>
      </button>
    </div>
  );
}
