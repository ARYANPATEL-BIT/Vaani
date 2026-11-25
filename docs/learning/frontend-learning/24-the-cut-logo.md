# 24. The new logo ("The Cut")

Branch: `feat/the-cut-logo` (uncommitted).

## 1. What

Vaani has a new logo, called "The Cut": वाणी in Devanagari, then VAANI in Latin capitals. The
vertical stroke of वा is a red bar that cuts through the top line of the letter, and VAANI ends
with a red square full stop. This change adds the logo as one React file and puts it in every
place that used to show an old mark: the landing page header, floating nav and footer, the
login header, the `/talk` icon rail and phone header, and the older sidebar used by `/enrol`
and `/loopback`. The browser tab icon (favicon) is now the logo's square icon. Frontend only.

## 2. Why

Before this, each page drew its own mark: typed text (वाणी, "Vaani", "Vaani.") in different
fonts and sizes, and in the older sidebar five animated bars, which is a generic "audio" icon
and not ours. The favicon was still Vite's purple lightning bolt from the project template.
One drawn logo, in one file, means every page shows the same mark and a later change is made
once. Nothing on the conversation path changed, so there is no latency number to give. The
production build still passes (`npm run build`); bundle size before and after was not compared.

## 3. How

**Two ideas first.**
- **SVG** (Scalable Vector Graphics) is a picture described as shapes ("a rectangle here, a
  curve there") instead of pixels. It stays sharp at any size and can be written straight into
  a React component, so its colours can come from props.
- A **knockout** is a shape painted in the background colour to make a gap in another shape.
  The logo's red bar does not just sit on वा: a small rectangle in the *paper* colour is
  painted over the top line first, so the line looks cut. That only works if "paper" is
  exactly the colour behind the logo. On a different background the knockout shows as a box.
  That is why the component takes both `ink` (the letter colour) and `paper` (the background).

**The files.**
- `frontend/src/components/brand/VaaniLogo.jsx` holds two components. `VaaniLogo` is the full
  wordmark; you give it a `height` and it works out its own width. `VaaniIcon` is the square
  app icon (an ink tile with वा and the red bar); you give it a `size`. The red is fixed;
  ink and paper are props. The shape data was supplied by the designer and is used as is.
- **Colours come from each page's own variables, not from hex codes.** Every page already
  turns its palette into CSS variables (`--lp-paper` on the landing page, `--tk-bg` on
  `/talk`, `--lg-bg` on login). The logo is given strings like `var(--tk-bg)`. The browser
  resolves them like any CSS colour, so when `/talk` switches to Ink (dark) mode, the
  variables change and the logo recolours itself with no extra code. On a dark background
  (the landing footer and floating nav) the props are simply passed the other way round:
  ink gets the paper colour and paper gets the ink colour.
- The older sidebar (`components/Sidebar.jsx`) has no palette of its own, so two new
  variables live in `theme/colors.css`: `--logo-ink` and `--logo-paper`, with light and dark
  values. Its background is frosted glass (semi-transparent white with blur), which no solid
  colour matches exactly; `--logo-paper` in light mode is a near-white picked to match it.
  The sidebar draws both the wordmark and the icon; `AppLayout.css` shows the wordmark when
  the sidebar is wide and the icon when it collapses to a rail (1100 px and narrower).
- **Where each version is used.** Full logo: landing header (36 px tall), login header (36),
  floating nav (22), footer (56), wide sidebar (28). Icon: `/talk` rail and phone header and
  the collapsed sidebar (28). The `/talk` rail is only 72 px wide and the full logo at 28 px
  tall is about 135 px wide, so the rail gets the icon.
- **Accessibility.** Each SVG has `role="img"` and a label, so a screen reader announces it as
  one picture. Where the logo sits inside a link, the link's own `aria-label` names where it
  goes ("Vaani home", or on the landing page "Vaani, back to top").
- `frontend/public/favicon.svg` is the icon as a plain SVG file; `frontend/index.html` points
  at it and adds a `theme-color` meta tag (the colour some phone browsers paint their toolbar).

## 4. When

Every time a page renders. There is no state and no network call: the logo is static shapes
whose two colours are read from CSS variables, so a theme switch recolours it on the next
paint. The favicon is loaded once by the browser when the page opens.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Logo as an inline React SVG component | A `logo.svg` file shown with an `<img>` tag | An `<img>` cannot take colours from the page, so the knockout could not follow the background or dark mode; we would need one file per background. |
| Colours from each page's CSS variables | The brand hex codes (#171513, #E6E0D5) everywhere | The pages' paper is #EEE9DF, not #E6E0D5. A hex knockout would show as a faint box, and dark mode would need extra code to swap props. |
| Icon in the 72 px `/talk` rail | The full logo, shrunk to fit the rail | At 72 px wide the full logo would be about 15 px tall, under the 18 px minimum where the letters stay readable. |
| SVG favicon only | Also PNG icons (180, 192, 512 px) for phone home screens | No PNG tool is installed (no sharp, rsvg-convert or ImageMagick) and adding one is a new dependency; modern browsers use the SVG. |

## 6. Known issues

- No PNG icons, so "Add to home screen" on iOS shows a screenshot instead of the logo.
- The sidebar's light-mode knockout is matched by eye to frosted glass; on a very different
  part of the background gradient a sub-pixel edge could show. Checked only in Chromium.
- The brand colours (#171513, #E6E0D5) differ slightly from the pages' palettes (#141312,
  #EEE9DF). The logo follows the pages; the favicon uses the brand values.
- The big decorative वाणी at the bottom of the footer and the preloader's वाणी are typography,
  not the logo, and were left as they are.
