/**
 * LandingPage -- the public page at "/" ("On Air" design). It puts the
 * sections together, turns the palette into CSS variables, and decides once
 * whether the loader plays (first visit in this browser session, and never
 * under reduced motion).
 *
 * It never asks for the microphone and never opens a WebSocket: the tape is
 * a scripted demo and every button leads to the real app at APP_PATH.
 *
 * router.jsx loads this file lazily, so its code, CSS, fonts and images are
 * a separate download that the voice app's pages never wait for.
 */

import { useCallback, useEffect, useState } from 'react';
import { CURSOR_HOTSPOT, HERO, IMAGES, PALETTE, PRELOADER, TAPE } from './landingContent.js';
import useReducedMotion from './useReducedMotion.js';
import Preloader from './Preloader.jsx';
import SiteNav from './SiteNav.jsx';
import Hero from './Hero.jsx';
import CutBand from './CutBand.jsx';
import Ticker from './Ticker.jsx';
import IdeaSection from './IdeaSection.jsx';
import StorySection from './StorySection.jsx';
import VoicesSection from './VoicesSection.jsx';
import ChainSection from './ChainSection.jsx';
import LatencySection from './LatencySection.jsx';
import ClosingSection from './ClosingSection.jsx';
import Footer from './Footer.jsx';
import './landing.css';
import './tape.css';
import './sections.css';

// PALETTE.paperDeep -> --lp-paper-deep, and so on. The stylesheets use only
// these variables, so every colour still comes from landingContent.js.
const kebab = (s) => s.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
const PAGE_VARS = {
  ...Object.fromEntries(Object.entries(PALETTE).map(([k, v]) => [`--lp-${kebab(k)}`, v])),
  // The scissors cursor over the tape: image, hotspot, then a fallback.
  '--lp-cursor': `url("${IMAGES.cursor}") ${CURSOR_HOTSPOT.x} ${CURSOR_HOTSPOT.y}, crosshair`,
  '--lp-letter-step': `${HERO.letterStepS}s`,
  '--lp-tape-h': `${TAPE.heightPx}px`,
  '--lp-pre-delay': `${PRELOADER.liftStartS}s`,
  '--lp-pre-lift': `${PRELOADER.liftS}s`,
};

// sessionStorage can throw (private windows, blocked site data); then we
// cannot remember, and the loader simply plays again.
function shouldPlayPreloader(reducedMotion) {
  if (reducedMotion) return false;
  try {
    return window.sessionStorage.getItem(PRELOADER.sessionKey) === null;
  } catch {
    return true;
  }
}

export default function LandingPage() {
  const reducedMotion = useReducedMotion();
  // Decided once, on the first render, so it does not flip mid-visit.
  const [playPreloader] = useState(() => shouldPlayPreloader(reducedMotion));
  const [preloaderDone, setPreloaderDone] = useState(false);
  const hidePreloader = useCallback(() => setPreloaderDone(true), []);
  // The tape's Pause button. Held here, not in LiveTape, because it also
  // stops the signal chain's running dot (.lp-paused in sections.css).
  const [paused, setPaused] = useState(false);
  const togglePause = useCallback(() => setPaused((p) => !p), []);

  useEffect(() => {
    if (!playPreloader) return;
    try {
      window.sessionStorage.setItem(PRELOADER.sessionKey, '1');
    } catch {
      // Storage blocked: nothing to remember it in.
    }
  }, [playPreloader]);

  const showPreloader = playPreloader && !preloaderDone;
  // How long the headline and the tape wait for the loader to lift.
  const leadS = playPreloader ? PRELOADER.leadS : 0;

  return (
    // .lp is its own scroll container: the app's global CSS sets
    // body { overflow: hidden }, so the page cannot scroll the body.
    <div className={paused ? 'lp lp-paused' : 'lp'} style={{ ...PAGE_VARS, '--lp-lead': `${leadS}s` }}>
      {/* Paper grain over everything. Decorative, and pointer-events: none
          in CSS so it never blocks a click. */}
      <svg className="lp-grain" aria-hidden="true">
        <filter id="lp-grain-f">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#lp-grain-f)" />
      </svg>
      {showPreloader && <Preloader onDone={hidePreloader} />}
      {/* inert: while the loader covers the page, nothing under it can be
          focused or clicked. id="top" is here, not on .lp: a "#top" link
          scrolls .lp to this element, and a scroll container never scrolls
          to reveal itself. */}
      <div id="top" inert={showPreloader}>
        <Hero reducedMotion={reducedMotion} leadS={leadS} paused={paused} onTogglePause={togglePause} />
        <main>
          <CutBand />
          <Ticker />
          <IdeaSection />
          <StorySection />
          <VoicesSection reducedMotion={reducedMotion} />
          <ChainSection />
          <LatencySection />
          <ClosingSection />
        </main>
        <Footer />
        <SiteNav />
      </div>
    </div>
  );
}
