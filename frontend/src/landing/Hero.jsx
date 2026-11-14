/**
 * Hero -- the dark top of the landing page: the header (SiteHeader), the
 * "SPEAK / Interrupt / LISTEN" headline, the call to action, the ribbon
 * wave and the scripted demo card with its pause button.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Mic, Pause, Play } from 'lucide-react';
import { APP_PATH, NAV_LINKS, HERO, DEMO } from './landingContent.js';
import { demoAt } from './demoScript.js';
import HeroWave from './HeroWave.jsx';
import DemoCard from './DemoCard.jsx';

export function LogoMark({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" fill="currentColor" aria-hidden="true">
      <rect x="3" y="7" width="3" height="8" rx="1.5" />
      <rect x="9.5" y="2" width="3" height="18" rx="1.5" />
      <rect x="16" y="6" width="3" height="10" rx="1.5" />
    </svg>
  );
}

// The top bar: logo, section links, and the two ways into the app.
export function SiteHeader() {
  return (
    <header className="lp-header lp-dark">
      <div className="lp-header-inner">
        <a href="#top" className="lp-logo">
          <LogoMark />
          <span>Vaani</span>
        </a>
        <nav aria-label="Sections" className="lp-nav">
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href}>{link.label}</a>
          ))}
        </nav>
        <div className="lp-header-actions">
          <Link to={APP_PATH} className="lp-pill">{HERO.openApp}</Link>
          <Link to={APP_PATH} className="lp-round" aria-label={HERO.cta}>
            <Mic size={18} strokeWidth={1.8} aria-hidden="true" />
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Hero({ paused, onTogglePause, reducedMotion, leadS }) {
  // Updated by HeroWave's loop when the demo text or phase changes.
  const [liveDemo, setLiveDemo] = useState(() => demoAt(0));
  const demo = reducedMotion ? demoAt(DEMO.stillFrameAt) : liveDemo;
  const [first, middle, last] = HERO.words;

  return (
    <section className="lp-hero lp-dark" aria-labelledby="lp-hero-title">
      <h1 id="lp-hero-title" className="lp-headline">
        <span className="lp-mask"><span className="lp-w1">{first}</span></span>
        <span className="lp-slash" aria-hidden="true">/</span>
        <span className="lp-mask"><span className="lp-w2 lp-serif">{middle}</span></span>
        <span className="lp-slash" aria-hidden="true">/</span>
        <span className="lp-mask"><span className="lp-w3">{last}</span></span>
      </h1>

      <div className="lp-hero-row">
        <p>{HERO.description}</p>
        <Link to={APP_PATH} className="lp-cta">
          {HERO.cta}
          <ArrowRight size={16} strokeWidth={2} aria-hidden="true" />
        </Link>
      </div>

      <div className="lp-wave">
        <HeroWave
          paused={paused}
          reducedMotion={reducedMotion}
          leadS={leadS}
          onDemoChange={setLiveDemo}
        />
      </div>

      <div className="lp-demo-wrap">
        <DemoCard demo={demo} />
        {/* Under reduced motion nothing moves, so there is nothing to pause.
            The label names what a click does, like the sidebar's theme
            toggle; no aria-pressed, which would say the same thing twice. */}
        {!reducedMotion && (
          <button type="button" className="lp-pause" onClick={onTogglePause}>
            {paused
              ? <Play size={14} strokeWidth={2} aria-hidden="true" />
              : <Pause size={14} strokeWidth={2} aria-hidden="true" />}
            {paused ? HERO.play : HERO.pause}
          </button>
        )}
      </div>
    </section>
  );
}
