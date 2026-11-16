/**
 * Ticker -- the red mono marquee. The phrase list is drawn twice in a row
 * and the strip slides left by exactly half its width, then jumps back:
 * because both halves are identical, the jump is invisible and the loop is
 * seamless. Decorative (every phrase is said elsewhere on the page), so it
 * is hidden from screen readers. It stops on hover and under reduced motion.
 */

import { BRAND, TICKER } from './landingContent.js';

function Phrases() {
  return (
    <span className="lp-tick-run">
      {TICKER.map((p) => (
        <span key={p}>
          {p === '<hindi>' ? <span className="lp-dv">{BRAND.hindiWord}</span> : p}
          {' ／ '}
        </span>
      ))}
    </span>
  );
}

export default function Ticker() {
  return (
    <div className="lp-ticker" aria-hidden="true">
      <div className="lp-tick lp-mono">
        <Phrases />
        <Phrases />
      </div>
    </div>
  );
}
