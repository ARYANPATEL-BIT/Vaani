# 23. The login page ("studio door")

Branch: `feat/login-page` (uncommitted).

## 1. What

A new page, `/login`, lets a visitor sign in with Google before using the voice app. It follows
the "studio door" design (`docs/design/login-studio-door/`): a black door with an ON AIR lamp
that is off, blinking, sliced or lit, depending on how the sign-in is going. `/talk` now sends
a signed-out visitor to `/login`, and its rail (or, on a phone, its settings sheet) has a Sign
out button. Frontend only: the backend's sign-in routes (`backend/vaani/auth.py`) are unchanged.

## 2. Why

The backend already refuses the voice WebSocket without a valid session cookie
(`backend-learning/22-google-auth.md`), but the browser had no way to get that cookie. With
auth on, Connect simply failed. Now there is a page that gets the cookie, and a guard that
sends people there.
Nothing was measured on the conversation path: the only new work on `/talk` is one background
request that does not delay the page. The production JavaScript bundle is 462.14 kB after this
change (from `npm run build`); the size before was not measured on this branch.

## 3. How

**Three ideas first.**
- An **ID token** is a short signed note from Google that says "this is user X, email Y, and
  this note is for app Z". Signed means Google's private key made it, so anyone can check it
  with Google's public keys, but nobody can forge it. Our backend checks that signature.
- **Google Identity Services (GIS)** is a script Google hosts that draws Google's own sign-in
  button and, when the user picks an account, hands our page an ID token. Google requires its
  own button, so we choose only its presets (outline, pill shape) and cannot restyle it.
- An **httpOnly cookie** is a cookie the browser keeps and sends by itself, but page
  JavaScript cannot read. Our session cookie `vaani_session` is one, so a malicious script
  injected into the page cannot steal it. The page never touches it: it only reads status
  codes.

**Cross-origin requests.** The page runs at `localhost:5173` and the API at `localhost:8000`.
A different port makes a different *origin*, and browsers limit what one origin may do with
another. **CORS** (Cross-Origin Resource Sharing) is the server saying which origins may call
it. Our backend allows `http://localhost:5173` and allows credentials. On our side,
`credentials: "include"` on every fetch tells the browser to store the cookie the answer sets,
and to send it next time. Without it, the cookie would be silently dropped.

**The flow.** `login/LoginPage.jsx` first asks `GET /auth/me` (`login/authApi.js`). If the
answer says we are in, or that auth is off, it goes on to `/talk`. Otherwise it shows the door.
`login/GoogleButton.jsx` adds the GIS script with one `<script>` tag, then asks Google to draw
its button. When Google hands over the ID token, the page shows "checking" and locks the
button, then posts the token to `POST /auth/google`. `login/loginState.js` is a pure function
(no browser, tested by `loginState.test.js`) that turns the answer into a view: `onair` on 200,
`refused` on "not invited" or "email not verified", `error` on everything else (Google
unreachable, token rejected, origin not allowed, server not answering). On air, the page opens
`/talk` after 1.5 s (`LOGIN_ONAIR_HOLD_MS` in `src/config.js`), or sooner with "Go to the
studio". The look is in `StudioDoor.jsx` (left), `LoginPanel.jsx` (right), `login.css` and
`loginContent.js` (all words and colours).

**The route guard.** A *route guard* is a check that runs when a page opens and sends the
visitor elsewhere if they may not be there. `login/RequireSignIn.jsx` wraps `/talk` in
`src/router.jsx`. It draws `/talk` at once and asks `/auth/me` in the background; only a 401
sends the visitor to `/login`. It is a courtesy, not the lock: the backend still checks the
cookie on every WebSocket.

**Sign out.** `login/useSignOut.js` posts `/auth/logout`. The server answers by deleting the
cookie (the page cannot, because it is httpOnly). Then it opens `/login`. Leaving `/talk`
unmounts that page, and the existing hooks' cleanup closes the mic and the socket.

## 4. When

- `/login` opens: one `GET /auth/me`. Then nothing, until the user clicks Google's button.
- After Google's account picker: one `POST /auth/google`, then the new view.
- `/talk` opens: one `GET /auth/me` in the background, every time the page is opened.
- Sign out: one `POST /auth/logout`.
- In development only, `/login?preview=off|checking|refused|error|onair` shows each view with
  no request at all (`login/loginPreview.js`, dropped from production builds).

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| GIS loaded with a plain `<script>` tag | The `@react-oauth/google` npm package | A new dependency to keep updated, for two function calls (`initialize`, `renderButton`) |
| Guard that draws `/talk` first and checks in the background | A React Router *loader* that checks before drawing | Every visit to `/talk` would wait for a round trip to the backend before showing anything |
| Pure `loginState.js` mapping the answer to a view | Status checks written inside the page component | Could not be tested with plain Node; every answer would need a browser to check |
| Google's own button for "Try again" / "Use another account" | Our own buttons with those labels, as in the mockups | Google's rules require its button for starting sign-in; ours would also need a second sign-in path (One Tap or a popup call) |
| A 1.5 s automatic move to `/talk`, plus a button | Wait for the button click only | One more click for every sign-in, after the page has already said "Opening the studio" |

## 6. Known issues

- Not signed in against Google yet: the local backend runs with auth off, so only the DEV
  previews were checked (1440 and 390 px). A real run needs a Google OAuth client with
  `http://localhost:5173` as an authorised origin, its ID in both `.env` files, and auth on.
- Google's button is 40 px tall, under our 44 px tap-target rule; we cannot resize its frame.
- With auth off, Sign out lands on `/login`, which sends the visitor straight back to `/talk`.
- The page is paper-only: it ignores Ink (dark) mode, because the design has no dark version.
- The guard's 401 path (redirect to `/login`) was not seen in a browser; only its pure
  function is tested.
