/**
 * CutBand -- "Say 'wait'." over a portrait that is cut through the mouth.
 *
 * The split uses two copies of the same image stacked exactly on top of
 * each other. clip-path shows only the top half of one and the bottom half
 * of the other, so together they look like one picture. On scroll (CSS
 * scroll-driven animation in sections.css) a red line draws across the
 * mouth, then the top copy slides left and the bottom copy slides right.
 * Without scroll-driven CSS, or under reduced motion, the picture stays
 * whole with the red line drawn.
 */

import { CUT_BAND, IMAGES } from './landingContent.js';

export default function CutBand() {
  const [before, red, after] = CUT_BAND.title;
  return (
    <section className="lp-cutband" aria-labelledby="lp-cut-title">
      <div className="lp-cutband-text">
        <p className="lp-mono lp-eyebrow">{CUT_BAND.eyebrow}</p>
        <h2 id="lp-cut-title" className="lp-cd lp-cutband-title">
          {before}<span className="lp-red-text">{red}</span>{after}
        </h2>
        <p className="lp-cutband-p">{CUT_BAND.text}</p>
      </div>
      <div className="lp-split">
        {/* The top half carries the real alt text; the bottom half is the
            same picture again, so it is hidden from screen readers. */}
        <img src={IMAGES.portrait} alt={CUT_BAND.alt} className="lp-half lp-half-top"
          loading="lazy" decoding="async" />
        <img src={IMAGES.portrait} alt="" aria-hidden="true" className="lp-half lp-half-bottom"
          loading="lazy" decoding="async" />
        <div className="lp-cutline" aria-hidden="true" />
        <span className="lp-mono lp-cut-tag" aria-hidden="true">{CUT_BAND.tag}</span>
      </div>
    </section>
  );
}
