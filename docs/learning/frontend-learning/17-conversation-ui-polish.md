# 17 - Conversation page: bigger text, a centred button, one scroll container

Working tree on `dev`, uncommitted. Frontend only; no backend, protocol or database change.

## 1. What

Three small changes to the conversation page. All text is about 10% bigger. The Start
Conversation button is centred on the page column (the area right of the sidebar), not on
the whole window. The "View Pipeline Latency Telemetry" link and the panel it opened
(`LatencyHud`) are gone. To centre the button properly, the app also gained its first real
scroll container: the page column now scrolls, where before nothing on the page could.

## 2. Why

- **Text size.** The page read small on a large screen. Nothing was measured; this is a
  visual request.
- **Button off-centre.** At 1280 px wide the button's centre was at x = 640 (the window's
  centre) while the page column's centre is at x = 742.5. The sidebar pushed it left.
- **The panel.** The backend sends no `telemetry` message (PROJECT.md, known gaps), so
  the panel never showed a number.
- **Nothing scrolled.** A *scroll container* is an element with `overflow: auto` or
  `scroll`: when its content is taller than the element, it shows a scrollbar. Checked in
  headless Chrome at 1280 x 800: `body` and `.app-shell` were both `overflow: hidden`, and
  no element between them and the page was a scroll container. The page was 931 px tall in
  an 800 px window, so its last 131 px (the bottom of the conversation card) was cut off
  with no way to reach it. These numbers come from a measuring script run during this PR,
  not a saved run file.

## 3. How

1. **One size dial.** CSS has a unit called `rem`: "a multiple of the root font size".
   The root font size is set once, on `:root` in `frontend/src/index.css`. Every text size
   on the conversation page is written in `rem`, so changing that one value from 15 px to
   16.5 px makes all of it 10% bigger. Example: the "Ready" title is `2rem`, so it went
   from 30 px to 33 px. Sizes written in `px` (the sidebar, icons) do not change.
2. **Keeping the pickers on one row.** At 1280 px the Persona, Mode and Reply pickers
   would have been about 3 px too wide after the bump. The gap between them in
   `.header-actions` (`frontend/src/pages/ConversationPage.css`) went from `1.25rem` to
   `1rem`. In the screenshot at 1280 x 800 all three share one row. The Disconnected chip
   was already on a second row before this change.
3. **The scroll container.** `frontend/src/components/AppLayout.jsx` now wraps every page in
   a `<main className="app-main">`. Its rule in `AppLayout.css` makes it exactly as tall as
   the window (`100vh`, the same unit `.app-shell` uses) and `overflow-y: auto`. The sidebar
   sits outside it, so it never moves; only the page column scrolls.
4. **Fixed versus sticky.** The button used to be `position: fixed`: placed relative to
   the window and outside the page layout, so `left: 0; right: 0` centred it on the window.
   It is now `position: sticky; bottom: 2rem`. A sticky element stays in the normal layout,
   but if scrolling would carry it below "2rem above the bottom of the visible area", it
   stops there and the content slides under it. That visible area belongs to the nearest
   scroll container above it. With no scroll container (the old layout) sticky has nothing
   to measure against, which is why step 3 had to come first.
5. **Bottom on tall screens.** On a 2560 x 1440 screen the page content ends long before
   the bottom, so nothing scrolls and sticky never moves the button. To still place it at
   the bottom: `.conversation-container` is a *flex column* (its children stack top to
   bottom) at least `100vh` tall, and the button's wrapper has `margin-top: auto`. In a flex
   column an auto margin takes all the leftover height, which pushes the button to the
   bottom. `padding-top: 1.5rem` keeps a gap so it never touches the card above.
6. **Centring.** The button's wrapper is the last child of `.conversation-container`, which
   is centred inside `.app-main`, so its own `justify-content: center` centres it on the
   column. No sidebar width appears anywhere. Below 1100 px the sidebar shrinks to 60 px,
   and the column recentres by itself.
7. **Panel removed.** `ConversationPage.jsx` no longer imports `LatencyHud` or calls
   `useLatencyTelemetry`; `LatencyHud.jsx` and `LatencyHud.css` are deleted. Kept on
   purpose: `src/hooks/useLatencyTelemetry.js`, `src/telemetry/latencyTelemetry.js` and
   `latencyTelemetry.test.js`. They parse the server `telemetry` message planned after
   phase 1. `LatencyCard.jsx` was already imported by nothing before this PR, and is left
   alone.

### Follow-up: root raised to 18px

The text was still small, so the root font size in `index.css` went from 16.5 px to 18 px
(about 9% more), app-wide. Examples: the hint line 15.7 to 17.1 px, transcript text 15.3 to
16.7 px. At 18 px the three pickers need 922 px in one row, more than the 888 px a 960 px
column leaves, so the column's `max-width` in `ConversationPage.css` went to 1020 px (26 px
spare at 1280 px wide). The other option was to keep the root and raise only the small
sizes in three CSS files so nothing is under 14 px. The single dial was chosen: one line,
every size keeps its proportion, and Enrol and Loopback grow with it. Measured in headless
Chrome at 1280 x 800 with 12 fake turns, scrolled to the bottom: the last line ends at
y = 640, the button starts at 696, so they do not overlap.

## 4. When

All of this is layout, worked out by the browser when a page renders, when the window is
resized and on every scroll. Nothing runs in JavaScript, and nothing touches the
conversation path: no WebSocket, audio or timing code changed.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| Change the root font size once in `index.css` | Edit `font-size` in every component's CSS | About 30 edits instead of 1, and any size someone missed would stay small, so the page would scale unevenly |
| Gap between pickers `1.25rem` to `1rem` | Widen the column's `max-width` from 960 px to 1000 px | Changes the width of the whole page (orb, card) to fix one row; kept as the fallback if Reply wraps |
| A scrolling `.app-main` around every page | Make `.conversation-container` scroll itself | The column is at most 960 px wide and centred, so on a 2560 px screen its scrollbar would float about 300 px left of the window edge |
| `sticky` plus `margin-top: auto` | Keep `fixed` and set `left: calc(sidebar width)` | The calc must know the sidebar is 205 px, or 60 px below 1100 px; any sidebar change would silently move the button off-centre again |
| Follow-up: root 18px plus a 1020px column | Keep the root; raise only sizes under 14px in three CSS files | About 15 separate edits, and the title and "Ready" would not grow, so the page's sizes would no longer keep their proportions |
| Keep the telemetry parser, its hook and its test | Delete them with the panel | The server `telemetry` message is planned after phase 1; deleting the tested parser now means rewriting it then |

## 6. Known issues

- The root font size applies app-wide: Enrol and Loopback text is also bigger (checked at
  16.5 px, not re-checked at 18 px); the sidebar is in `px` and unchanged.
- At 18 px some small labels are still under 14 px (message time 12.6, pill labels and
  turn count 13.5).
- Pickers at 1280 px: 922 of 948 px measured. Narrower than about 1255 px with the full
  sidebar, Reply wraps onto the status chip's row.
- Enrol pages had `overflow-y: auto` and used to scroll inside themselves. Inside
  `.app-main` they grow with their content, so only `.app-main` scrolls (one scrollbar).
- Space in push-to-talk is stopped from scrolling (`PttButton.jsx` cancels it). In
  hands-free mode the PTT handler is not mounted, so Space can scroll `.app-main`. That is
  ordinary browser behaviour and was not changed.
- Checked in headless Chrome with fake turns added in the browser only. No live session
  with the backend was run, and `ConversationPage.css` (496 lines) is still over the
  ~300-line limit.
