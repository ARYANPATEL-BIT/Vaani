/**
 * SiteNav -- the floating ink pill docked at the bottom of the screen:
 * the वाणी mark (back to top), the section links (hidden under 640 px in
 * CSS) and a Start talking pill.
 */

import { Link } from 'react-router-dom';
import { APP_PATH, HERO, NAV_LINKS } from './landingContent.js';
import { VaaniLogo } from '../components/brand/VaaniLogo.jsx';
import Arrow from './Arrow.jsx';

export default function SiteNav() {
  return (
    <nav className="lp-nav" aria-label="Main">
      <a href="#top" className="lp-nav-mark" aria-label={HERO.backToTop}>
        <VaaniLogo height={22} ink="var(--lp-paper)" paper="var(--lp-ink)" />
      </a>
      <div className="lp-nav-links">
        {NAV_LINKS.map((l) => (
          <a key={l.href} href={l.href} className="lp-mono lp-nav-link">{l.label}</a>
        ))}
      </div>
      <Link to={APP_PATH} className="lp-mono lp-pill">{HERO.cta}<Arrow /></Link>
    </nav>
  );
}
