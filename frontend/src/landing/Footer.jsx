/**
 * Footer -- name, section links and credits, over a ribbed glow strip.
 */

import { FOOTER, NAV_LINKS } from './landingContent.js';

export default function Footer() {
  return (
    <footer className="lp-dark lp-footer">
      <div className="lp-inner lp-footer-inner">
        <div className="lp-footer-brand">
          <span className="lp-serif lp-footer-name">{FOOTER.name}</span>
          <span lang="hi" className="lp-footer-hindi">{FOOTER.nameHindi}</span>
          <span className="lp-muted-sm">{FOOTER.tagline}</span>
        </div>
        <nav aria-label="Footer" className="lp-footer-col">
          <span className="lp-footer-label">{FOOTER.exploreLabel}</span>
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href}>{link.label}</a>
          ))}
        </nav>
        <div className="lp-footer-col">
          <span className="lp-footer-label">{FOOTER.builtByLabel}</span>
          <span>{FOOTER.builtBy}</span>
        </div>
      </div>
      <div className="lp-footer-strip" aria-hidden="true" />
    </footer>
  );
}
