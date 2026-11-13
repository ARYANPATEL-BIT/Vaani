# 18 - Dark mode: one attribute on html, colours as CSS variables

Branch `feat/dark-mode`, uncommitted. Frontend only; no backend, protocol or database change.
Part 1 of 2: sidebar, conversation page and the toggle. Part 2 converts Loopback, Enrol and 404.

## 1. What

The app now has a light and a dark theme, and a "Dark mode" button in the sidebar footer,
above Operator. Dark follows the reference image `docs/design/dark-mode-reference.png`:
near-black page, grey instead of purple, a white Start button. With no saved choice the app
follows the operating system's light or dark setting. Light mode looks the same as before.

## 2. Why

- **It was asked for**, as a monochrome dark theme matching the reference image.
- **The old half-built theme crashed the app.** `AppLayout.jsx` read `localStorage` (see
  section 3) with no protection. In a browser where site data is blocked, that read throws an
  error. Checked in headless Chrome with storage blocked: the old code showed React Router's
  "Unexpected Application Error!" screen instead of the app. The new code renders normally.
- **The old theme also flashed.** It applied the theme after React's first paint, so a
  dark-mode user would have seen the light page for a moment on every load.

## 3. How

1. **CSS variables.** A CSS variable (a "custom property") is a named value such as
   `--cta-bg`. You define it once and use it anywhere as `var(--cta-bg)`. If the definition
   changes, every use changes with it. Before this PR, colours were typed directly into
   each rule (a "hardcoded" colour): about 205 of them in the files this part touches.
2. **Where they live.** The new file `frontend/src/theme/colors.css` holds every colour
   that differs between the themes. Its `:root` block (`:root` means the `<html>` element)
   holds the light values, copied unchanged from the old rules. Its `[data-theme="dark"]`
   block redefines the same names with dark values. `AppLayout.css`, `ConversationPage.css`,
   `VoiceOrb.css` and `TranscriptView.css` now say `var(--name)` where they had a colour.
   Colours that are the same in both themes stay where they were: status green, amber and red,
   the red push-to-talk "holding" state, and the orb sphere itself.
3. **One switch.** `data-theme` is an attribute on `<html>`. A CSS rule that starts with
   `[data-theme="dark"]` only applies while `<html>` has `data-theme="dark"`. So changing that
   one attribute recolours the whole app at once. No React component reads the theme.
4. **`color-scheme`.** This CSS property tells the browser which theme its own parts should
   use: scrollbars, form controls, the default page colour. `colors.css` sets it to `light`
   or `dark` alongside the variables, so scrollbars turn dark too.
5. **Remembering the choice.** `localStorage` is a small key-value store the browser keeps
   per website across visits. The choice is saved under the key `vaani-theme` as `light` or
   `dark`. Every read and write is wrapped in try/catch (code that catches an error instead
   of letting it crash the app). If storage is blocked, the theme still switches but is
   forgotten on reload.
6. **Following the system.** `prefers-color-scheme` is a question CSS and JavaScript can ask
   the browser: "is the operating system in dark mode?". It is only used when nothing is saved.
7. **The helper.** `frontend/src/theme/theme.js` has four small functions: read the saved
   value, decide the theme (saved value wins, else the system), set `data-theme` on `<html>`,
   and save. Storage is passed in as a function that returns it, because in Chrome even
   reaching `window.localStorage` throws when site data is blocked. `theme.test.js` (16 checks,
   part of `npm test`) uses a fake storage object, including ones that throw.
8. **No flash.** `frontend/index.html` has a script of about six lines inline in its `<head>`.
   The browser runs it before it draws anything and before React loads, so the first paint
   already has the right theme. It repeats the logic of `theme.js` because it cannot import a
   module that early. Both files carry a "keep in sync" note. A content security policy (a
   rule that can forbid inline scripts) would block it; none is set in `index.html`,
   `vite.config.js` or the backend.
9. **The toggle.** `Sidebar.jsx` holds the theme in React state, starting from what the
   inline script set. A click sets the attribute, saves the choice and updates the button. It
   is a real `<button>`, so it is reachable with Tab. Its label names what a click will do:
   moon + "Dark mode" in light, sun + "Light mode" in dark. A fixed "Dark mode" read like a
   status in dark mode. `aria-label` (the name a screen reader speaks) repeats the visible text.
   There is no `aria-pressed` (an on/off state for toggle buttons), because a name that changes
   plus an on/off state would contradict each other. In the 68 px sidebar (under 1100 px wide)
   only the icon shows, and `title` gives the same text as a hover tooltip. The focus ring is
   on `:focus-visible`, not `:focus`: the browser shows it after Tab, not after a mouse click. The old theme state and the unused `toggleTheme` in `AppLayout.jsx` are gone.
10. **Sidebar sizing.** CSS has two kinds of length. `px` is a fixed size. `rem` is a multiple
   of the root font size, which `index.css` raised from 16 px to 18 px so page text grew. The
   sidebar is written in `px`, so it did not grow with it, and next to the bigger page it
   looked small and cramped. It stays in `px` on purpose: lucide icons take their size as a px
   number, and the icons only line up, and stay centred in the narrow rail, if every row's
   icon column is an exact width. So the sizes were raised by hand, about 10 to 15 percent:
   width 205 to 230 px, collapsed rail 60 to 68 px (both in `index.css`), wordmark 18 to 20,
   logo 28 to 32 tall, nav text 14.5 to 16, icons 18 to 20, rows 42 to 46 px tall.
   One `ICON_SIZE = 20` in `Sidebar.jsx` sizes every icon, the operator avatar is 20 px to
   match, and `.sidebar` in `AppLayout.css` defines `--row-pad` and `--row-font` once, which
   the nav rows and all three footer rows use. So every icon has its centre 38 px from the
   left edge (34 px when collapsed). The theme toggle also needed `line-height: inherit`: the
   browser gives a `<button>` its own line height, which made it 5 px shorter than a nav row
   (37 against 42). The footer rows are 8 px apart, under the existing divider line. When collapsed they
   are 44 px squares and the operator chevron is hidden. At 1280x800 the three pickers on
   the conversation page still fit on one line: the page column is capped at 1020 px, and
   the main column is 1050 px wide, so it is still capped (measured in headless Chrome).

## 4. When

The inline script runs once per page load, before the first paint. The toggle runs on click.
Everything else is CSS the browser applies whenever the attribute changes. Nothing runs on
the conversation path: no WebSocket, audio, push-to-talk or orb animation code changed.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| CSS variables switched by one attribute | A theme library (for example `next-themes`) | A new dependency for about 40 lines of our own code; it is built for Next.js server rendering, which we do not use |
| Plain CSS variables in `colors.css` | A CSS-in-JS theme provider (colours in a JS object passed through React context) | Every component would need rewriting to read colours from JS, and a theme change would re-render the whole tree instead of the browser just recolouring |
| One `colors.css` for all themed colours | Each component file defines its own variables at its top | `ConversationPage.css` is already 497 lines; one file also shows the whole dark palette in one place |
| Inline script in `index.html` | Set the theme in a React effect (the old way) | An effect runs after the first paint, so dark-mode users see a light flash on every load |
| Saved choice, else the system setting | Always start in light | A user with a dark operating system would get a bright page until they find the toggle |
| Sidebar sizes in `px`, raised by hand | Rewrite them in `rem`, so they grow with the root automatically (205 px is 12.8 rem, 230 px at 18 px) | Icon sizes are px props, so icons and text could drift apart, and the collapsed rail needs exact widths to keep icons centred; we give up the sidebar following a future root change on its own |

## 6. Known issues

- Light mode was checked by comparing the computed colour, border, shadow and gradient of
  every element against a clean copy of `dev`, on 7 page/size combinations: no differences.
  The only differences were the animated opacity of the orb halos and logo bars, and
  `color-scheme` going from `normal` to `light`. That run was not saved to a file.
- Lowest contrast in dark: grey `#a3a3a3` timestamps on the `#262626` user bubble, 6.00:1
  (4.5:1 is the minimum for body text). Disabled nav rows are 4.28:1. White on the orange end
  of the push-to-talk "holding" gradient is 2.80:1, the same as light mode. Computed, not saved.
- Live-session states (Speak, holding, End, error banners, messages) were restyled but only
  seen idle; they were not seen with a running backend.
- Until part 2, Loopback, Enrol and 404 look half-dark in dark mode.
- After a click, the saved choice always wins; there is no "follow system again" option.
