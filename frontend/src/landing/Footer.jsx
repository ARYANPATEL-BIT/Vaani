/**
 * Footer -- name and tagline, the section links, credits and the IST clock,
 * then a huge वाणी cropped by the bottom edge.
 */

import { BRAND, CLOCK, FOOTER, NAV_LINKS } from './landingContent.js';
import useIstClock from './useIstClock.js';

export default function Footer() {
  const clock = useIstClock();
  return (
    <footer className="lp-footer lp-on-ink">
      <div className="lp-wrap lp-footer-grid">
        <div className="lp-footer-col">
          <span className="lp-cd lp-footer-name">{BRAND.latin}</span>
          <span className="lp-muted lp-footer-tag">{FOOTER.tagline}</span>
        </div>
        <nav aria-label="Footer" className="lp-mono lp-footer-nav">
          {NAV_LINKS.map((l) => <a key={l.href} href={l.href}>{l.label}</a>)}
        </nav>
        <div className="lp-mono lp-muted lp-footer-col">
          <span>{FOOTER.builtBy}</span>
          <span>{CLOCK.label} {clock}</span>
        </div>
      </div>
      <p className="lp-dv lp-footer-mark" aria-hidden="true">{BRAND.hindi}</p>
    </footer>
  );
}
