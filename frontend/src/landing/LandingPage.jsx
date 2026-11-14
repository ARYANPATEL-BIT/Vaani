/**
 * LandingPage -- the public page at "/". It puts the sections together and
 * owns the three page-wide switches: whether the preloader plays, whether
 * the visitor has paused the animation, and reduced motion.
 *
 * It never asks for the microphone and never opens a WebSocket: every
 * button leads to the real app at APP_PATH (landingContent.js).
 *
 * router.jsx loads this file lazily, so its code, CSS and fonts are a
 * separate download that the voice app's pages never wait for.
 */

import { useCallback, useEffect, useState } from 'react';
import { ACCENT, PRELOADER } from './landingContent.js';
import useReducedMotion from './useReducedMotion.js';
import Preloader from './Preloader.jsx';
import Hero, { SiteHeader } from './Hero.jsx';
import WhatSection from './WhatSection.jsx';
import InterruptSection from './InterruptSection.jsx';
import PipelineSection from './PipelineSection.jsx';
import LatencySection from './LatencySection.jsx';
import ClosingSection from './ClosingSection.jsx';
import Footer from './Footer.jsx';
import './landing.css';
import './sections.css';

// Play the preloader only on the first visit in this browser session.
// sessionStorage can throw (private windows, blocked site data); then we
// cannot remember, and it simply plays again.
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
  const [paused, setPaused] = useState(false);
  const hidePreloader = useCallback(() => setPreloaderDone(true), []);
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
  // How long the headline waits before its words rise (CSS reads --lp-lead).
  const leadS = playPreloader ? PRELOADER.leadS : 0;

  return (
    // .lp is its own scroll container: the app's global CSS sets
    // body { overflow: hidden }, so the page cannot scroll the body.
    <div
      className={paused ? 'lp lp-paused' : 'lp'}
      style={{
        '--lp-accent': ACCENT,
        '--lp-lead': `${leadS}s`,
        '--lp-pre-delay': `${PRELOADER.fadeStartS}s`,
        '--lp-pre-fade': `${PRELOADER.fadeS}s`,
      }}
    >
      {showPreloader && <Preloader onDone={hidePreloader} />}
      {/* inert: while the preloader covers the page, nothing under it can
          be focused or clicked, so a keyboard user cannot tab into links
          they cannot see.
          id="top" is here, not on .lp: the logo's "#top" link scrolls .lp
          to bring this element into view, and a scroll container never
          scrolls to reveal itself. */}
      <div id="top" inert={showPreloader}>
        <SiteHeader />
        <main>
          <Hero
            paused={paused}
            onTogglePause={togglePause}
            reducedMotion={reducedMotion}
            leadS={leadS}
          />
          <WhatSection reducedMotion={reducedMotion} />
          <InterruptSection />
          <PipelineSection reducedMotion={reducedMotion} />
          <LatencySection />
          <ClosingSection />
        </main>
        <Footer />
      </div>
    </div>
  );
}
