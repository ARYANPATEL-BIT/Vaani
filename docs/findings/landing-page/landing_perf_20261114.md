# Landing page: bundle size and wave frame time (2026-11-14)

Branch: feat/profiles-ui (landing page work). Machine: the developer's Mac,
macOS 15 (Darwin 24.3.0). Browser: Playwright's headless Chromium, which
renders canvas in software and runs rAF at 120 Hz. These are not phone numbers.

## 1. Bundle size (`npm run build`, Vite 8.3.0)

| File | Before (no landing page) | After |
|---|---|---|
| App JS `index-*.js` | 419.58 kB (gzip 127.15 kB) | 420.08 kB (gzip 127.43 kB) |
| App CSS `index-*.css` | 56.50 kB (gzip 11.81 kB) | 56.50 kB (gzip 11.81 kB) |
| Landing JS `LandingPage-*.js` | none | 24.97 kB (gzip 8.58 kB) |
| Landing CSS `LandingPage-*.css` | none | 13.90 kB (gzip 3.70 kB); 13.77 kB (gzip 3.68 kB) before the responsive fixes |
| Fonts (woff2, not gzipped) | none | 44.87 kB Inter Tight + 22.12 kB Instrument Serif |

The app's own JS grew by 0.50 kB (gzip 0.28 kB): the router's lazy import and
the fallback element. A direct load of `/talk` requested only `/talk`,
`index-*.js` and `index-*.css`: no landing chunk and no font.

## 2. Wave draw cost: mockup draw() against our port

Bench page: the mockup's `draw()` (copied from `docs/design/landing/Main.dc.html`)
and `drawRibbons.js` + `canvasSize.js`, run in the same page, same canvas
(viewport width x 440 px), 230 frames each, first 30 dropped, two rounds each.
"JS only" is the time to issue the drawing commands; Chrome paints them later,
so it undercounts. "With flush" adds `getImageData` each frame, which forces the
paint but adds a GPU read-back, so it overcounts. Milliseconds per frame,
mean (p95), round 1 / round 2.

| Setup | Canvas px | Mockup JS only | Port JS only | Mockup with flush | Port with flush |
|---|---|---|---|---|---|
| 1440 wide, DPR 1 | 1440x440 | 0.34 (0.5) / 0.29 (0.4) | 0.33 (0.5) / 0.30 (0.4) | 14.49 (15.2) / 14.52 (14.8) | 14.50 (14.8) / 14.51 (14.8) |
| 1440 wide, DPR 2 | 2880x880 | 0.36 (0.5) / 0.29 (0.4) | 0.33 (0.5) / 0.30 (0.4) | 44.68 (45.8) / 45.42 (47.2) | 44.88 (45.9) / 45.66 (47.2) |
| 390 wide, DPR 3, CPU slowed 4x | 780x880 | 0.60 (1.1) / 0.51 (0.9) | 0.62 (1.1) / 0.52 (1.0) | 53.06 (56.1) / 52.97 (55.5) | 52.94 (55.5) / 53.22 (55.7) |

The port costs the same as the mockup. At DPR 3 the canvas is 2x, not 3x:
the cap works.

## 3. Frames delivered on the real page

3 s of rAF timestamps on `/` (preloader skipped), wave running, then paused.

| Setup | Wave canvas px | Running: fps, p50 / p95 ms, frames > 20 ms | Paused |
|---|---|---|---|
| 1440, DPR 1 | 1440x440 | 120.3, 8.3 / 8.4, 0 | 120.7, 8.3 / 8.4, 0 |
| 1440, DPR 2 | 2880x880 | 120.3, 8.3 / 8.4, 0 | 119.7, 8.3 / 8.6, 0 |
| 390, DPR 3, CPU 4x | 780x560 | 120.3, 8.3 / 9.2, 0 | 120.3, 8.3 / 9.3, 0 |

Headless Chromium does not hold back rAF while it paints, so this shows the
main thread is free, not that a real phone's GPU keeps up. Not measured: a
real phone, a real GPU, battery use.

## 4. Pausing (rAF callbacks counted per second, 1440 wide)

Running 120; "Pause animation" pressed 0 (canvas pixels and demo text
unchanged); resumed 120; hero scrolled off screen 0; back on screen 121;
tab hidden (simulated: `document.hidden` overridden and `visibilitychange`
fired) 0; visible again 121. Reduced motion: 0 rAF callbacks, 0 running CSS
animations. getUserMedia calls on the landing page: 0. WebSockets opened: 0.
