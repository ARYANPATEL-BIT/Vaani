/**
 * VoicesSection -- "03 Voices": DEFAULT, TUTOR and SUPPORT as giant outlined
 * names (real buttons with aria-pressed), and a card for the chosen one
 * with a waveform, its mood and text, and a sticker on the corner. The
 * waveform and the sticker move once when the voice changes, then stay still.
 *
 * The choice rotates every VOICES.rotateMs on its own until the visitor
 * picks one. It also holds still while the pointer or keyboard focus is in
 * the section (so it never changes under someone reading it) and under
 * reduced motion.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { APP_PATH, BRAND, VOICES } from './landingContent.js';

const pad = (n) => String(n).padStart(2, '0');

// The card's waveform for each voice: bar heights from the voice's seed,
// fixed for the page's life, so it is worked out once here.
const BARS = VOICES.list.map(({ seed }) =>
  Array.from({ length: VOICES.bars }, (_, k) => ({
    h: Math.round((Math.abs(Math.sin(k * 0.61 * seed + seed)) * 0.75 + 0.25) * 64),
    red: k % 7 === 3,
    delay: ((k * 0.11 * seed) % 0.9).toFixed(2),
  })),
);

export default function VoicesSection({ reducedMotion }) {
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState(false);
  const [holding, setHolding] = useState(false);

  useEffect(() => {
    if (picked || holding || reducedMotion) return;
    const id = setInterval(() => setIndex((i) => (i + 1) % VOICES.list.length), VOICES.rotateMs);
    return () => clearInterval(id); // cleanup: stop rotating
  }, [picked, holding, reducedMotion]);

  const voice = VOICES.list[index];
  const hold = () => setHolding(true);
  const release = () => setHolding(false);

  return (
    <section id="voices" className="lp-voices-sec" aria-labelledby="lp-voices-title"
      onMouseEnter={hold} onMouseLeave={release} onFocus={hold} onBlur={release}>
      <div className="lp-wrap lp-voices">
        <div className="lp-voice-names">
          <h2 id="lp-voices-title" className="lp-mono lp-eyebrow">
            {VOICES.eyebrow}<span className="lp-dv">{BRAND.hindiWord}</span>
          </h2>
          {VOICES.list.map((v, i) => (
            <button key={v.name} type="button" aria-pressed={i === index}
              className={i === index ? 'lp-cd lp-vname lp-vname-on' : 'lp-cd lp-vname'}
              onClick={() => { setPicked(true); setIndex(i); }}>
              <span className="lp-mono lp-vname-idx">{pad(i + 1)}</span>{v.name}
            </button>
          ))}
        </div>

        <div className="lp-voice-card">
          {/* key: a new image element per voice. A new element starts its CSS
              animation from 0%, so the sticker's movement plays once per change. */}
          <img key={voice.name} src={voice.img} alt="" aria-hidden="true" decoding="async"
            className={`lp-sticker lp-motion-${voice.motion}`} />
          {/* Same trick for the bars: a new row per voice, so they grow once. */}
          <div key={`bars-${voice.name}`} className="lp-vbars" aria-hidden="true">
            {BARS[index].map((b, k) => (
              <span key={k} className={b.red ? 'lp-vbar lp-vbar-red' : 'lp-vbar'}
                style={{ height: `${b.h}px`, animationDelay: `${b.delay}s` }} />
            ))}
          </div>
          <p className="lp-voice-mood">{voice.mood}</p>
          <p className="lp-voice-text">{voice.text}</p>
          <div className="lp-voice-foot">
            <span className="lp-mono lp-muted">{VOICES.languages}<span className="lp-dv">{BRAND.hindiWord}</span></span>
            <Link to={APP_PATH} className="lp-mono lp-pill">{VOICES.talkTo} {voice.name}</Link>
          </div>
        </div>
      </div>
    </section>
  );
}
