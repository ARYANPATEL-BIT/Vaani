# Landing page "On Air": bundle size and frame pacing (2026-11-16)

Branch: feat/landing-on-air. Machine: the developer's Mac, macOS 15 (Darwin
24.3.0). Build: `npm run build` (Vite 8.3.0). Browser: Playwright's headless
Chromium, serving the production build with `vite preview`. These are not
phone numbers.

## 1. Bundle size

"Before" is a build of `dev` at 9aea1e7 (the old landing page), run on this
branch before any change. "After" is the final build of this branch.

| File | Before | After |
|---|---|---|
| App JS `index-*.js` | 428.58 kB (gzip 129.77 kB) | 428.54 kB (gzip 129.75 kB) |
| App CSS `index-*.css` | 60.46 kB (gzip 12.43 kB) | 60.46 kB (gzip 12.43 kB), same file hash |
| Landing JS `LandingPage-*.js` | 24.81 kB (gzip 8.50 kB) | 30.04 kB (gzip 10.34 kB) |
| Landing CSS `LandingPage-*.css` | 13.90 kB (gzip 3.70 kB) | 20.74 kB (gzip 4.81 kB) |
| Landing fonts (woff2) | 66.99 kB (Inter Tight 44.87 + Instrument Serif 22.12) | 231.91 kB (Archivo 90.10 + JetBrains Mono 21.16 + 21.83 + Tiro Devanagari Hindi 98.82) |
| Landing images | none | 732.49 kB (portrait 304.46, radio 104.29, reel 101.76, notebook 81.69, chai 78.62, spanner 52.65, cursor 9.02) |

The app's JS changed by -0.04 kB: only the hashed file name of the landing
chunk inside the router's lazy import changed. A direct load of `/talk`
requested `/talk`, `index-*.js` and `index-*.css` from our server (plus the
Google Fonts the app already loaded before this branch): no landing chunk,
no landing font and no landing image.

## 2. Frame pacing with the tape running

The hero on screen, the tape loop running, 3 s of `requestAnimationFrame`
timestamps, DPR 1 (headless). Chromium ran rAF at 120 Hz.

| Viewport | Canvas px | Frames in 3 s | Median gap | p95 gap | Max gap |
|---|---|---|---|---|---|
| 1440 x 900 | 1228 x 250 | 363 | 8.3 ms | 8.9 ms | 10.5 ms |
| 360 x 780 | 228 x 250 | 362 | 8.3 ms | 9.2 ms | 9.3 ms |

No frame took longer than about 1.3 refresh intervals. Not measured: DPR 2,
a slowed CPU, a real phone, and the cost of the full-screen grain overlay
on its own.

## 3. Behaviour checks (same session)

- The tape loop stops while the canvas is off screen and while paused: two
  canvas snapshots 0.8 s apart were identical in both cases.
- `/` created no WebSocket and made no `getUserMedia` call (both wrapped and
  counted for the whole visit: 0 and 0).

## 4. Radio call to action and one-shot voice motion (same day, later)

Same machine and Vite. "Before" is the build of this branch just before the
change, "after" the build just after it. Checks ran on the Vite dev server in
headless Chromium at DPR 1.

| File | Before | After |
|---|---|---|
| Landing JS `LandingPage-*.js` | 30.04 kB (gzip 10.34 kB) | 31.45 kB (gzip 10.87 kB) |
| Landing CSS `LandingPage-*.css` | 20.74 kB (gzip 4.81 kB) | 21.68 kB (gzip 5.03 kB) |
| App JS `index-*.js` | 428.54 kB (gzip 129.75 kB) | 428.54 kB (gzip 129.75 kB) |
| App CSS `index-*.css` | 60.46 kB (gzip 12.43 kB) | 60.46 kB (gzip 12.43 kB) |

- The visible radio in `radio.webp` (alpha above 24 of 255) is 76.4% of the
  image's width and 92.3% of its height, starting 11.6% from the left and
  3.7% from the top.
- Measured dial panel, as a % of the radio box, at 360, 390, 768, 1440 and
  1920 px: 52.1 / 38.9 / 28.9 / 18.5 at every width. The label was inside the
  panel at all five. Horizontal overflow of the page and of `.lp`: 0 px at all five.
- Label font size: 19 px at 360 and 390, and 37 px at 768, 1440 and 1920.
  Radio box 408, 448, 760, 760 and 760 px.
- Hover at 1440: the needle went from 13% to 72% of the dial at 480 ms and
  85% at 1.3 s, and was back at 13% 30 ms after the pointer left. The pulse
  ran once. With the pointer away, no animation ran in the closing section
  for 2 s.
- Voice card, auto-rotating: the sticker's animation lasted under 1 s after
  each change, and the bars' under 2 s. After that, neither had any animation.
- Contrast (WCAG formula, palette values): ink on dial 14.61:1, red text
  #B8240A on dial 5.02:1, ink on paper 15.34:1.
