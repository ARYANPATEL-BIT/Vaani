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
   is a real `<button>`, so it is reachable with Tab. Its accessible name is always "Dark mode",
   and `aria-pressed` (true or false) tells a screen reader whether it is on. The icon is a moon
   in light mode and a sun in dark mode. In the 60 px sidebar (under 1100 px wide) only the
   icon shows. The old theme state and the unused `toggleTheme` in `AppLayout.jsx` are gone.

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
