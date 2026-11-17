/**
 * ClosingSection -- the radio is the call to action. One link wraps the
 * radio image and the drawings laid over it: a cream dial panel reading
 * "START / TALKING" with tick marks and a red needle, a ring on the speaker
 * grille, and a focus ring around the radio itself.
 *
 * Every overlay is placed in percentages of the image's box (numbers in
 * CLOSING, landingContent.js), so it stays on the dial at every width.
 * Motion happens only on hover or keyboard focus, in sections.css
 * (.lp-radio-cta): the needle slides once, the grille pulses once.
 */

import { Link } from 'react-router-dom';
import { APP_PATH, CLOSING, IMAGES } from './landingContent.js';

// { left: 52.1, ... } -> { left: '52.1%', ... } for an inline style.
const pct = (box) => Object.fromEntries(Object.entries(box).map(([k, v]) => [k, `${v}%`]));

// The label's font size as a straight line through the two (box width,
// font size) points, clamped at both ends. 100cqw is the radio box's own
// width (the link is a size container in CSS), so the text scales with the
// radio, not with the window.
const { atBox: [b0, b1], size: [s0, s1] } = CLOSING.labelPx;
const LABEL_SIZE = `clamp(${s0}px, calc(${s0}px + (100cqw - ${b0}px) * ${(s1 - s0) / (b1 - b0)}), ${s1}px)`;

// Box width: wide enough that the visible radio fills the column (the
// transparent margins hang over the sides), capped on desktop.
const BOX_WIDTH = `min(${CLOSING.maxBoxPx}px, ${(100 / CLOSING.visible.width) * 100}%)`;
// The box keeps the image's shape even before the (lazy) image arrives or
// if it fails, so the page does not jump and the dial keeps its place.
const BOX_RATIO = `${CLOSING.imagePx.width} / ${CLOSING.imagePx.height}`;

export default function ClosingSection() {
  return (
    <section className="lp-closing">
      <div className="lp-wrap lp-closing-inner">
        <p className="lp-mono lp-muted lp-closing-text">{CLOSING.text}</p>

        {/* One link. Everything inside is aria-hidden, so a screen reader
            hears only the aria-label, once. */}
        <Link to={APP_PATH} className="lp-radio-cta" aria-label={CLOSING.ariaLabel}
          style={{ width: BOX_WIDTH, aspectRatio: BOX_RATIO }}>
          <img src={IMAGES.radio} alt="" aria-hidden="true" loading="lazy" decoding="async"
            className="lp-radio-img" />
          <span className="lp-radio-grille" aria-hidden="true" style={pct(CLOSING.grille)} />
          <span className="lp-radio-ring" aria-hidden="true" style={pct(CLOSING.visible)} />
          <span className="lp-dial" aria-hidden="true" style={pct(CLOSING.dial)}>
            {/* Real text, not part of the picture: sharp at any size,
                and the font and colour come from CSS. */}
            <span className="lp-cd lp-dial-label" style={{ fontSize: LABEL_SIZE }}>
              {CLOSING.label.map((line) => <span key={line}>{line}</span>)}
            </span>
            <span className="lp-dial-ticks" />
            <span className="lp-dial-needle" />
          </span>
        </Link>

        <Link to={APP_PATH} className="lp-mono lp-closing-link">{CLOSING.smallLink}</Link>
      </div>
    </section>
  );
}
