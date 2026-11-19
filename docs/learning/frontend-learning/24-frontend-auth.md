# 24. Frontend auth: one origin, and a gate before the page

Branch: `feat/frontend-auth` (uncommitted).

## 1. What

The browser now reaches the backend through the page's own address. Vite's dev server forwards
`/auth`, `/health` and `/ws` to the backend (a *proxy*), and every URL in the frontend is
relative. `/talk` and every sidebar page (`/enrol/*`, `/loopback`, the 404 page) now check
`GET /auth/me` *before* they are drawn, and send a signed-out visitor to `/login`. The sidebar
shows who is signed in and has a working Logout. A refused voice socket sends a signed-out user
to `/login`. `/login` has a dark (Ink) version. No backend code changed.

## 2. Why

Before this, the page lived on `localhost:5173` and called `localhost:8000` directly. That only
worked on one machine: through a Cloudflare tunnel (a public https address for your laptop),
the phone's browser cannot reach `localhost:8000` at all, and the cookie had no way to follow.
The old guard (`23-login-page.md`) drew `/talk` first and checked afterwards, so a signed-out
visitor saw the page flash, and the enrol pages had no check at all.
Measured cost of the proxy (`docs/findings/frontend-auth/proxy_20261118.txt`): about 3.5 ms at
p50 on the WebSocket handshake, once per session, and about 0.2 ms at p50 per message after
that. Mic-stop to first audio was not measured (it needs a Playwright tool not available here).

## 3. How

**Origin and site.** An *origin* is scheme + host + port: `http://localhost:5173` and
`http://localhost:8000` are two origins. Browsers keep origins apart: a page may not read
another origin's answers unless that server allows it (*CORS*). A *site* is looser: roughly the
scheme and the domain, ignoring the port. Our cookie `vaani_session` is `SameSite=Lax`: the
browser sends it only on requests the same site starts (plus plain link clicks from elsewhere).
That is what stops another website from using it.

**The proxy.** A *proxy* is a server that takes a request and passes it on to another server.
`frontend/vite.config.js` tells Vite's dev server: anything under `/auth`, `/health` or `/ws`
goes to the backend (`VAANI_PROXY_TARGET`, default `http://localhost:8000`); `ws: true` also
forwards WebSocket upgrades. To the browser there is now one origin, so the cookie is sent on
every call and on the socket by itself, with no CORS and no `credentials: "include"`. The proxy
does not rewrite the `Origin` header, so the backend's check (`auth.py`, `allowed_origins`)
still sees the real page address. `server.allowedHosts` lets Vite answer requests for any
`*.trycloudflare.com` address; by default it refuses unknown host names, as a guard against a
trick called DNS rebinding. `npm run preview` gets the same proxy.

**Relative URLs.** `src/api/authApi.js` calls `/auth/me`, `/auth/google`, `/auth/logout`.
`sessionSocketUrl()` in `src/config.js` builds the socket address from the page's own host:
`ws:` on an http page, `wss:` (encrypted) on an https one such as the tunnel, because a browser
refuses plain `ws:` from an https page. The same build works on localhost and on any tunnel. The
old `VITE_API_BASE_URL` and `VITE_WS_SESSION_URL` are gone: Vite bakes `VITE_` values into the
code at build time, so the tunnel address would have needed a rebuild every run.

**The gate.** A *loader* is a function React Router runs, and waits for, before it shows a
route; it is possible because `src/router.jsx` uses a "data router" (`createBrowserRouter`).
`src/login/requireSignIn.js` is that loader for `/talk` and for the sidebar layout. It asks
`/auth/me`: on 401 it *throws* a redirect to `/login` (the router's way of saying "go there
instead"), so the page is never drawn. On 200 it returns the user, or `{email: null}` when auth
is off; the page reads it with `useLoaderData()`. On the first load, a blank screen
(`hydrateFallbackElement`) shows during the check; later, the old page stays until it is done.

**Cutting the check short.** An *abort signal* is a cancellation token for a fetch: when it
fires, the request is dropped. The gate combines two with `AbortSignal.any`: the router's own
signal (the visitor navigated away) and `AbortSignal.timeout(5000)` (`AUTH_CHECK_TIMEOUT_MS`).
A hung or broken backend lets the visitor in as nobody; the socket's error then says what is
wrong. Only a clear 401 counts as "signed out".

**Who is shown.** `operatorFor()` in `src/login/loginState.js` turns the gate's answer into a
name, an initial and `signedIn`. `components/Sidebar.jsx`, `talk/RailNav.jsx` and
`talk/StudioHeader.jsx` use it: "Operator" and no Logout when auth is off.

**A refused socket.** When the backend refuses the handshake (HTTP 403), the browser hides it
and reports a bare failure, the same as a server that is down. So `hooks/useAudioCapture.js`,
when the socket fails before it ever opened, asks `/auth/me`: 401 opens `/login`, anything else
shows the usual connection error.

**Dark /login.** `login/loginContent.js` has PAPER and INK palettes (INK reuses
`talk/talkContent.js` values); `LoginPage.jsx` picks by `data-theme`, as `/talk` does. Google's
button is `outline` on paper and `filled_black` on ink (`GoogleButton.jsx`).

**The cookie's Secure flag.** `secure_cookie` stays `false` on localhost, because the page is
plain http there. It is set `true` in `backend/.env` (`VAANI_AUTH__SECURE_COOKIE=true`) only
for the tunnel, which is https. Never in `config.toml`.

**Sign in, but no Sign up.** Two separate questions: *who are you* (identity) and *may you come
in* (access). Your Google account answers the first, so there is no account for Vaani to create.
The backend's allowlist answers the second, and only the team can add an email to it, so a
"Sign up" button would promise something no visitor can do. The landing header (`Hero.jsx`)
shows Sign in only after `/auth/me` answers 401, via `landingAuthFor` in `loginState.js`.

## 4. When

- First load of `/talk` or a sidebar page: one `GET /auth/me`, before the page is drawn.
- Every later move into those routes: one `GET /auth/me` again; leaving mid-check aborts it.
- Connect on `/talk`: the socket opens on the page's host; only if it fails before opening,
  one extra `GET /auth/me`.
- Logout: one `POST /auth/logout`, then `/login`.
- `/` and `/login`: no gate. `/` sends one `GET /auth/me` after it draws, never waits for it.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| One origin through Vite's proxy, cookie stays `SameSite=Lax` | Two origins with a `SameSite=None; Secure` cookie and CORS | The backend would need its own tunnel address, added to CORS each run; a `None` cookie is sent on requests from any site, so it leans on the Origin check alone; and browsers treat it as a third-party cookie (Safari blocks those by default) |
| Relative URLs built from `window.location` | `VITE_` URL variables per environment | Baked in at build time: a new tunnel address would need an edit and a rebuild |
| A loader that checks before drawing | The old guard that draws, then checks (`23-login-page.md`) | Signed-out visitors saw the page flash. The worry then was the wait; `/auth/me` through the proxy measured 5.2 ms p50 with curl (findings file above) |
| Gate on the whole sidebar layout | A nested route around the enrol pages only | One more route level for no gain: `/loopback` and the 404 page need no public access |
| Treat no answer or a timeout as "let in" | Treat it as signed out and go to `/login` | A backend that is down would look like a sign-in problem, and sign-in would not fix it |
| `/login` layout: header, main and footer padded by `--lg-gutter` = `max(24px, (100% - 1312px) / 2)`, so content sits in the landing page's 1360 px column (`.lp-wrap`); a 55/45 grid, the door at 4:3 capped by the window height; at 960 px and under the text stacks above the door (CSS `order`) | An inner wrapper `<div>` in each of the three, like `.lp-wrap` | Same result, but it changes the JSX; the padding keeps the border lines full width and the change in `login.css` alone |

## 6. Known issues

- Not run in a browser: the gate, the refused-socket path, dark `/login` and a real Google
  sign-in were checked only by tests, lint and a build. No screenshots were taken.
- The `/login` wide-screen layout fix was not checked in a browser either (no Chrome
  extension in that session); whether it fits 1280x800 without scrolling is unverified.
- A quick tunnel gets a new address each run: add it to `VAANI_AUTH__ALLOWED_ORIGINS` and to the
  Google client's authorised origins, then restart the backend, every time.
- Mic-stop to first audio through the proxy was not measured; only the socket's own timings were.
- `enrolApi.js` calls `/api/enrol/*`, which the backend does not have and the proxy does not
  forward: those calls fail, as before.
- `useAudioCapture.js` is 561 lines, well over the 300-line limit.
