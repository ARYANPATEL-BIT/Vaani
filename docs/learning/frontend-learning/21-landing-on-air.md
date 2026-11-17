# 21. The landing page, redesigned ("On Air")

Branch: `feat/landing-on-air`.

## 1. What

The landing page at `/` is rebuilt from the "On Air" design (`docs/design/landing-on-air/`): a
paper-and-ink radio look, a scripted two-track "live tape" you can cut into, a portrait that splits
through the mouth as you scroll, sections on the idea, cutting in, the three voices, the signal
chain and the latency target. The closing call to action is the radio picture itself. Routing,
lazy loading and `/talk` are unchanged. All code is in `frontend/src/landing/`.

## 2. Why

The old page explained interrupting, but the visitor could only watch it. The tape lets them press
"Cut in" and see Vaani stop mid-word where they pressed. Motion that runs on its own and tells no
story (a humming radio, floating stickers) was cut. The app's JS and CSS did not grow. The landing
download is 31.45 kB JS, 21.68 kB CSS, 231.91 kB of fonts and 732.49 kB of images
(`docs/findings/landing-page/landing_on_air_perf_20261116.md`). End-to-end latency is not measured.

## 3. How

**Where things live.** `landingContent.js` holds every word, colour, timing, voice, image URL and
overlay position. `LandingPage.jsx` assembles the sections, one file each (`Hero.jsx`,
`CutBand.jsx`, `VoicesSection.jsx`, `ClosingSection.jsx`, ...). Styles are in `landing.css`,
`tape.css` and `sections.css`. Every rule starts with `.lp`, so nothing leaks onto `/talk`.

**The tape.** A *canvas* is a rectangle of pixels that JavaScript paints. `requestAnimationFrame`
asks the browser to call a function before each screen refresh, which gives a drawing loop.
- `useTape.js` runs that loop. It keeps `t` (seconds into the demo) and `cut` (the second the user
  cut in). Each frame adds the time since the last one, capped at 50 ms, so a hidden tab resumes
  instead of jumping ahead.
- `demoScript.js` is pure: given `(t, cut)` it returns captions, phase and speaker. Every time after
  the cut is an *offset* from it, so moving `cut` re-times everything after it. **Cut in** sets
  `cut = t`, and Vaani's caption freezes at the characters typed so far plus "…"
  (`demoScript.test.js` checks a cut at 2.0 s).
- `drawTape.js` stores no bars. Bar k was spoken at k × gap and has slid left since, so its place is
  computed each frame, and its track comes from asking `demoScript.js` who spoke then.
- The loop runs only if not paused, the tab is visible and the tape is on screen. The Pause state
  lives in `LandingPage.jsx`, which adds `.lp-paused` to the page, so the same button also stops the
  signal chain's running dot. Over the tape the pointer is a scissors image (`cursor.png`) whose
  *hotspot*, the pixel that counts as the click, is the blade tips.

**Scroll-driven animation** (all in `sections.css`). A normal CSS animation follows the clock; a
scroll-driven one follows scrolling. Its *view timeline* is 0% when an element starts to enter the
screen and 100% when it has left; `animation-range` picks a slice. The split portrait (two stacked
copies, each `clip-path`-ed to one half), the idea words (each its own slice, in reading order) and
the rolling latency digits all use it.

**IntersectionObserver** is a browser API that says "this element entered or left an area", without
measuring on every scroll. `useActiveStep.js` makes the area a thin band across the middle, and
whichever story step crosses it becomes active.

**The radio link** (`ClosingSection.jsx`, styles under "Closing" in `sections.css`).
- One `<a href="/talk">` wraps the image and three drawings on top of it: the cream dial panel
  (label, ticks, a red needle made of a 3 px box), a circle on the speaker grille, and a focus ring.
  The drawings are `aria-hidden`, so a screen reader hears only "Start talking: open the Vaani app".
- *Percent overlay.* The link has the image's exact shape: its width is set and `aspect-ratio`
  gives the picture's 640 × 431 shape. Each drawing is `position: absolute` with left, top, width and height
  in % of that box. When the box grows or shrinks, the picture and the % positions scale by the same
  factor, so the panel stays on the dial window at any width. Nothing is measured in JavaScript.
- *Sizing.* The image has transparent margins: the radio is 76.4% of its width (measured from the
  alpha channel). The box is `min(760px, 100% / 0.764)` of the column, so the radio fills a phone
  and the empty margins hang over the edges. `overflow-x: clip` on the section cuts them off without
  creating a scroll box. The focus ring hugs the radio, not the box, so it stays on a phone screen.
- *Label size.* The link is a *size container*: inside it, `100cqw` means "this box's width". The
  font is a straight line from 19 px at a 450 px box to 37 px at 760 px, so it scales with the radio.
- *Why real text.* Text baked into the picture would blur when scaled, could not change colour on
  hover, and could not be read by a screen reader or a translation tool.
- *Hover, CSS only.* `:hover` and `:focus-visible` give the needle `left: 86%` plus a 0.9 s
  *transition* (a smooth slide between two values). The transition is on the hover state only, so
  leaving has none and the needle snaps back. The grille gets a one-run `box-shadow` animation (a
  ring that grows and fades); an animation added on hover starts again each time hover starts.
  Press scales by 0.985. All of it sits inside `prefers-reduced-motion: no-preference`.

**Replaying an animation by keying.** A CSS animation runs when an element first gets it. React's
`key` names an element; when the key changes, React throws the old element away and creates a new
one. `VoicesSection.jsx` keys the sticker and the waveform row by the voice's name, so each change
(a click or the 4.5 s auto-rotate) creates new elements whose one-run animation plays, then stops.

**If something fails.**
- Radio image missing or still loading: `aspect-ratio` keeps the box's shape, so the page does not
  jump and the dial and label still show in place (tested with the image blocked).
- No scroll-driven CSS (Firefox today): words lit, portrait whole, digits on their final value.
- Reduced motion: no loader, one still tape frame, no needle slide, pulse or sticker movement. The
  label still turns red on hover.
- If the loader's animation never runs, a timer removes it anyway.

## 4. When

The landing chunk loads when someone opens `/`. The loader plays once per browser session. The tape
draws every frame while visible and not paused. Voices rotate every 4.5 s until one is picked; the
sticker and bars move once per change. The radio moves only on hover or keyboard focus.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Canvas tape drawn from `(t, cut)` | About 150 SVG bars and a stored list | Hundreds of elements updated each frame, and a moved cut would mean rewriting history |
| CSS scroll-driven split, words, digits | A JS scroll listener setting styles | Code on every scroll event plus cleanup, for an effect CSS already does |
| IntersectionObserver for the active step | Measuring each step on every scroll | Layout reads on every scroll event, which can stutter |
| `overflow: clip` on the band, digits and closing | `overflow: hidden` | `hidden` makes a scroll container, which the view timeline would track instead of the page |
| Deeper red #B8240A for red text on paper | The design's #FF3B1C everywhere | About 2.9:1 on paper, below the 4.5:1 text minimum |
| Radio overlays in % of the image box | Fixed px positions with breakpoints | Right only at the tested widths; between them the label drifts off the dial |
| Label as HTML text over the picture | "START TALKING" painted into radio.webp | Blurs when scaled, cannot change colour, invisible to screen readers |
| CSS `:hover` / `:focus-visible` sequence | JS events starting a timeline | More code, and keyboard focus would need its own listener |
| Keying the sticker and bars per voice | Removing and re-adding a class in JS | Needs a forced layout read between the two steps to restart; hard to follow |
| `new URL(..., import.meta.url)` for images | `import img from './x.webp'` | The Node test imports `landingContent.js` and would crash loading an image |

## 6. Known issues

- Checked only in headless Chromium at DPR 1: no Safari, Firefox, real phone or touch testing.
- On touch screens the radio has no hover preview; a tap goes straight to `/talk`.
- "Talk to Tutor" opens plain `/talk`; it does not pre-select that voice.
- The portrait (304 kB) is the largest file and has no smaller size for phones.
- The app's `index-*.js` prints the enrolment-consent test suite to the console (from before).
