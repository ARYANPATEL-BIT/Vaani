# 20. The landing page

Branch: `feat/profiles-ui` (the landing page part; the profiles work on this branch is separate).

## 1. What

Vaani now has a public landing page at `/`, built from the design mockup
`docs/design/landing/Main.dc.html`. It has a short preloader, a hero with the
headline "SPEAK / Interrupt / LISTEN", an animated ribbon wave, a scripted demo
card, and sections on what Vaani is, interrupting, the pipeline, latency, a
closing call to action and a footer. The voice app moved from `/` to `/talk`.
All landing code lives in `frontend/src/landing/`.

## 2. Why

The app opened straight onto the conversation screen, with nothing to tell a
visitor what Vaani does or why interrupting it matters. The landing page says
that, then sends every button to the app. It must not slow the app down. The app's
JavaScript grew by 0.50 kB (gzip 0.28 kB), and a direct load of `/talk` fetches
no landing code or fonts (`docs/findings/landing-page/landing_perf_20261114.md`).
The measured P50 latency is not known yet, so the page shows the project's
target ("<1,000 ms") and a marked "not measured yet" placeholder.

## 3. How

**Routing.** `frontend/src/router.jsx` has two top-level routes. `/` loads
`landing/LandingPage.jsx` lazily: the browser downloads it only when someone
visits `/`, as a separate chunk (its own JS file in the build). Every other page
sits under `AppLayout` (the sidebar) as before, the conversation page at
`/talk`. The sidebar, 404 and enrol pages' "back to conversation" go there.

**One file of content.** `landing/landingContent.js` holds every word, the
accent colour, the nav links, the demo script and its timings, the wave
settings, and `measuredP50Ms`. Set that number there (with its run file in
`measuredSource`) to replace the placeholder.

**The scripted demo.** `landing/demoScript.js` turns a time in the 14 s loop
into the three transcript lines and the phase (speak, cut, listen, think,
idle). No timers; `demoScript.test.js` checks every boundary.

**The wave, step by step.**
- A *canvas* is a rectangle of pixels the page draws on with JavaScript, like
  a painting. Unlike normal HTML, nothing in it is an element: to change the
  picture you clear it and paint again.
- `requestAnimationFrame` (rAF) asks the browser to call a function just
  before it paints the next frame, usually 60 times a second. The function
  draws one frame and asks again, which makes a loop that matches the screen.
- `landing/HeroWave.jsx` runs that loop. Each frame it advances the demo clock,
  eases the wave's height toward the phase's target (`stepWave` in
  `drawRibbons.js`: tall while speaking, almost flat the instant it is cut),
  and draws with `drawRibbons`. When the demo text changes, it passes the
  new lines up to `Hero.jsx`, which shows them in `DemoCard.jsx`. The wave and
  the words read the same clock, so they stay in step.
- `drawRibbons.js` paints three ribbons. Each is the area between two wavy
  curves, with fine strands across it and glowing edges. It draws with
  *additive blending* (the canvas mode called "lighter"): where two strokes
  overlap, their colours add up, so overlaps grow brighter and whiter, as light
  does. Wide faint strokes under a thin bright one make the glow, which is much
  cheaper than a blur filter.
- `landing/canvasSize.js` matches the canvas to sharp screens (the *device
  pixel ratio*, DPR: real pixels per CSS pixel) but caps it at 2 and at 3,400
  pixels across: a soft glow does not need 9x the pixels.

**Effect cleanup.** In React, an *effect* is code that runs after the
component is on screen, to start things React does not manage: the rAF loop,
observers and event listeners. The effect returns a *cleanup* function, which
React runs when the component leaves the page and before running the effect
again. The wave's cleanup cancels the pending frame (`cancelAnimationFrame`),
disconnects its observers and removes its listener. Without it, every visit or
pause would leave one more loop drawing into a canvas that may no longer exist.

**Pausing.** The loop runs only while four things are true: the visitor has
not pressed "Pause animation", the hero is on screen (an
*IntersectionObserver*, a browser callback for "this element entered or left
the visible area"), the tab is visible (the `visibilitychange` event), and
motion is allowed: drawing what nobody sees wastes battery and CPU. The
preloader (`landing/Preloader.jsx`, about 3.7 s) needs no such code: a hidden
tab gets no rAF calls, and its counter is computed from elapsed time.

**Scroll reveal.** A *scroll-driven animation* is a CSS animation whose
progress follows scrolling instead of the clock: `animation-timeline: view()`
in `landing.css` makes each section rise in as it enters the view, with no
JavaScript. It sits inside `@supports`, so a browser without it (Firefox
today) simply shows the content.

**Reduced motion.** When the visitor has asked their system for less motion,
`useReducedMotion.js` says so: no preloader, one still frame of the wave with
the full transcript, no pause button, no reveal, no pipeline auto-advance and
no cursor blob. The pipeline's step bar is a CSS animation whose end moves to
the next step, so hovering, focusing or pausing just stops that animation.

**Styles.** Every rule in `landing.css` and `sections.css` starts with `.lp`:
Vite never unloads a stylesheet, so the prefix keeps landing styles off `/talk`.
The fonts (Inter Tight, Instrument Serif) are woff2 files in `landing/fonts/`,
with their OFL licences, from Fontsource 5.3.0.

## 4. When

The landing chunk loads when someone opens `/`; the preloader plays once per
browser session (a `sessionStorage` flag); the wave runs every frame while the
four pause conditions allow it; the reveal runs as each section scrolls in.
Nothing of it runs on `/talk`.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Canvas 2D for the wave | SVG paths redrawn each frame | About 90 strand paths rewritten in the page every frame, and additive blending in SVG depends on uneven browser support, so the glow would not match |
| CSS scroll-driven reveal inside `@supports` | IntersectionObserver adding a class | More JavaScript and observers to clean up, and it only fires once instead of following the scroll |
| Self-hosted woff2 fonts | `@fontsource` npm packages | Two new dependencies for two files we can keep ourselves |
| Landing at `/`, app at `/talk` | Landing at `/welcome`, app stays at `/` | Moves no links, but a visitor to the site's address never sees the landing page |
| Lazy route for the landing page | Import it with the other pages | The app's main JS would carry about 25 kB more (`landing_perf_20261114.md`) |
| One rAF loop for wave and demo text | A separate timer for the text | Two clocks drift, and the ribbons would flatten before or after the words stop |
| CSS animation end advances the pipeline | A `setInterval` timer | Pausing on hover would need extra code to stop and restart the timer and the bar together |

## 6. Known issues

- Frame cost was measured only in headless Chromium, which renders in software: about 14.5 ms per forced paint at 1440x440 and 45 ms at 2880x880 (`landing_perf_20261114.md`). Real phone: not measured. Tab hiding was simulated, not done for real.
- The frosted demo card blurs the animating canvas behind it every frame; its share of the cost was not measured on its own.
- The app's global CSS still loads Inter, Fraunces, Newsreader and Plus Jakarta Sans from Google's CDN on every page, including this one.
