/**
 * WhatSection -- "What it is": the title and three cards (it speaks, you cut
 * in, it listens), each with a little bar waveform. On a desktop with a
 * mouse, a round accent "cursor blob" follows the pointer over the cards.
 */

import { useRef } from 'react';
import { ACCENT, WHAT } from './landingContent.js';
import { LogoMark } from './Hero.jsx';

const BAR_COUNT = 30;

// Heights and colours of one card's bars. speak: a tall pulsing hump; cut:
// all flat but one accent spike; listen: a small hump with an accent centre.
function bars(kind) {
  const out = [];
  for (let i = 0; i < BAR_COUNT; i++) {
    const d = (i - 14.5) / 14.5;
    const envelope = Math.exp(-d * d * 3.2);
    const wobble = Math.abs(Math.sin(i * 1.7 + 1));
    let h = 5;
    let colour = '#0B0B0B';
    if (kind === 'speak') h = 5 + envelope * 120 * (0.4 + 0.6 * wobble);
    if (kind === 'cut' && i === 15) { h = 150; colour = ACCENT; }
    if (kind === 'listen') {
      h = 5 + envelope * 38 * wobble;
      if (Math.abs(d) < 0.2) colour = ACCENT;
    }
    // Staggered delays so the pulsing bars do not all move together.
    out.push({ h: Math.round(h), colour, delay: `${((i * 0.07) % 1.2).toFixed(2)}s` });
  }
  return out;
}

export default function WhatSection({ reducedMotion }) {
  const blobRef = useRef(null);

  // The blob moves by setting a CSS transform directly on the element: no
  // React re-render per mouse move. React's onMouseMove props are removed
  // with the element, so there is no listener to clean up by hand.
  const pointer = reducedMotion ? {} : {
    onMouseMove: (e) => {
      blobRef.current.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`;
    },
    onMouseEnter: () => { blobRef.current.style.opacity = '1'; },
    onMouseLeave: () => { blobRef.current.style.opacity = '0'; },
  };

  return (
    <section id="what" className="lp-light" aria-labelledby="lp-what-title">
      <div className="lp-inner lp-stack-40">
        <div className="lp-eyebrow-row">
          <span className="lp-eyebrow">{WHAT.eyebrow}</span>
          <span className="lp-rule" />
        </div>
        <div className="lp-reveal lp-what-head">
          <h2 id="lp-what-title" className="lp-h2">
            {WHAT.title[0]}<span className="lp-serif">{WHAT.title[1]}</span>{WHAT.title[2]}
          </h2>
          <svg aria-hidden="true" width="64" height="64" viewBox="0 0 64 64" fill="none" stroke="#0B0B0B" strokeWidth="1.2">
            <circle cx="32" cy="22" r="14" /><circle cx="32" cy="32" r="14" /><circle cx="32" cy="42" r="14" />
          </svg>
        </div>
        <div className="lp-cards" {...pointer}>
          {WHAT.cards.map((card, index) => (
            <article key={card.num} className={`lp-card lp-card-${index}`}>
              <div className="lp-card-art">
                <span className="lp-serif lp-card-num">{card.num}</span>
                <div className="lp-bars" aria-hidden="true">
                  {bars(card.kind).map((b, i) => (
                    <span
                      key={i}
                      className={card.kind === 'speak' ? 'lp-bar lp-bar-pulse' : 'lp-bar'}
                      style={{ height: b.h, background: b.colour, animationDelay: b.delay }}
                    />
                  ))}
                </div>
              </div>
              <h3>{card.name}</h3>
              <p>{card.text}</p>
            </article>
          ))}
        </div>
      </div>
      <div className="lp-cursor" ref={blobRef} aria-hidden="true">
        <LogoMark size={26} />
      </div>
    </section>
  );
}
