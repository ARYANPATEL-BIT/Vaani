# 22 - Google sign-in: only allowlisted accounts can use Vaani

Branch `feat/google-auth` (from `dev`, uncommitted). Protocol v0.10 -> **v0.11** (`contracts.md` 2.9).

## 1. What

Until now anyone who could reach the server could open `/ws/session` and spend our free LLM
quota. Now a user must sign in with a Google account that is on our **allowlist** (a fixed
list of email addresses, `[auth] allowed_emails`). The server gains three HTTP routes,
`POST /auth/google`, `GET /auth/me` and `POST /auth/logout`, and the WebSocket handshake
is refused unless it carries our session cookie and comes from our own web page. This is
the backend half; the login page is the frontend commit (`frontend-learning/21-login.md`).

## 2. Why

Groq's free tier is shared by everyone holding the key (`PROJECT.md`, known gaps). One
stranger's script could use the day's requests, and every real user would then get
failover to Gemini or `LLM_FAILED`. The spend cap (`spend.py`) limits how much is spent,
not who spends it. The allowlist makes sure only people we chose get through. Sign-in
itself is checked by Google, so we store no passwords.

Measured (`docs/findings/google-auth/handshake_20261116.txt`): the check on the handshake
takes 0.017 ms at p50 (0.028 p95) inside the server. Connect to `session.started` was
1.37 / 1.44 ms p50 with auth on, against 1.34 ms with it off in the same sitting. The
mic-stop to first-audio path is untouched. **Not measured:** a real sign-in against Google.

## 3. How

1. **The ID token.** Google's sign-in button (frontend) asks the user to pick an account,
   then hands the page an **ID token**: a JWT (JSON Web Token: a short text holding
   facts such as `email` and `sub`, Google's fixed id for the person, signed with Google's
   private key). Anyone can check the signature with Google's published public keys
   (its "certificates"), but only Google can make one.
2. **Sign-in route.** `google_sign_in` in `backend/vaani/auth.py`. It refuses an `Origin`
   header not in `[auth] allowed_origins`. It then calls `verify_google`, which uses
   **google-auth** (Google's own library, imported only in this file) to check the
   signature, the expiry, the issuer and that the token's audience is OUR client ID, so a
   token another website obtained is useless here. google-auth downloads Google's
   certificates on every call and blocks while it does. So the route runs it with
   `asyncio.to_thread` (a worker thread from Python's default pool, not the ASR or TTS
   pools), and the event loop keeps serving every live audio session. Our 5 s timeout
   (`google_timeout_s`) bounds it; the library's own default is 120 s.
3. **Allowlist.** The token's `email_verified` must be true, and its email, lowercased,
   must be in `allowed_emails`. Failures answer `401` or `403` with an `AUTH_*` code in the
   socket's error shape (`protocol.py`, `contracts.md` 2.9).
4. **Our cookie.** On success, `sign_cookie` builds `sub|email|expiry|name`, base64url-encodes
   it (cookies must be ASCII; names need not be) and appends an **HMAC-SHA256** of it. An
   HMAC is a fingerprint computed from the text plus a secret key
   (`VAANI_AUTH__SESSION_SECRET`): change one character, or use another key, and the
   fingerprint no longer matches. So the cookie needs no database row; the signature
   proves we wrote it. It is `HttpOnly` (page JavaScript cannot read it), `SameSite=Lax`
   (not sent on requests started by other sites) and lasts `cookie_days` (7).
5. **Reading it back.** `read_cookie` checks the signature with `hmac.compare_digest`, which
   takes the same time wherever the first wrong character is, so timing cannot reveal
   the right one. Only then does it decode the text, check the expiry and check the
   email is still allowed. `GET /auth/me` returns the name and email, or `401`.
6. **The handshake.** `handshake_refusal` (`auth.py`) is called in `gateway.py` before
   `accept()`. A browser attaches our cookie to a WebSocket opened by ANY page, even
   evil.example's: that attack is **cross-site WebSocket hijacking**. WebSockets are
   not covered by CORS, so the server must look itself: the browser always sends the
   real `Origin` of the page, and a page cannot change it. Bad origin or bad cookie:
   the gateway closes before accepting, uvicorn answers HTTP 403 and no socket opens.
7. **CORS.** The page (`localhost:5173`) and the server (`localhost:8000`) are different
   origins, so `app.py` adds FastAPI's `CORSMiddleware` with `allowed_origins` and
   `allow_credentials`: that is the browser's permission to send the cookie and read
   our answers.
8. **Startup.** `create_app` calls `check_settings`: auth enabled but no client ID, a
   secret missing or under 32 characters, or an empty allowlist or origin list, and the
   server refuses to start, naming the variable, never its value.

## 4. When

- **Server start:** settings checked; CORS and the routes are registered.
- **Sign-in** (about once a week per user): one Google certificate download, on a thread.
- **Every `/ws/session` connection:** one Origin compare and one HMAC, before accept.
- **Every `/auth/me`:** one HMAC. Logout clears the cookie in the browser only.

## 5. Alternatives

| Chosen | The alternative | Why not the alternative |
|---|---|---|
| ID token from the button, checked by us | OAuth authorization-code flow (Google redirects back with a one-time code; our server swaps it, with a client secret, for tokens) | Needs a client secret, a redirect route and a second HTTP call to Google. That flow is for acting on the user's Google data (Drive, Gmail); we only need to know who they are |
| google-auth to verify | Our own JWT check with `cryptography` and Google's key list | Signature, audience, issuer and expiry rules written by us: the classic place for an auth bug. Cost: a vendor library, so CLAUDE.md now names `auth.py` |
| HMAC cookie, `HttpOnly` | A JWT kept in `localStorage`, sent in a header by our JavaScript | Any script running in the page (an XSS bug) can read `localStorage` and steal the token; it cannot read an `HttpOnly` cookie. And a browser cannot set headers on a WebSocket, so the token would have to go in the URL, where it lands in logs |
| No sessions table | A `sessions` row per sign-in, looked up on each request | A database read on every handshake, a schema change (`user_version` 1 to 2, and `db.py` has no migrations). Cost: no early revocation (section 6) |
| Origin + cookie check before accept | Accept, then ask for a token in the first message | The socket, its pipeline and its task would exist for strangers; and the cookie would still ride along on a hijacked socket |
| `asyncio.to_thread` for Google | Call it directly in an `async` route | The download blocks the one event loop: every session's audio would stall for up to the timeout |
| No certificate cache | `CacheControl` around google-auth's HTTP session | Another dependency to save one download a week per user |
| Email not stored in the database | A `user_email` column on `sessions` | Same migration cost as above, and personal data in the file. Deferred until History needs it |

## 6. Known issues

- No early revocation: a copied cookie works until it expires (7 days). Removing the
  email from the allowlist or changing the secret stops it, after a restart.
- A cookie that expires mid-conversation is only seen at the next connect; the browser
  cannot read the 403 (it sees close code 1006). Frontend follow-up.
- Scripts such as `fake_client.py` and `measure_turn.py` send no cookie or Origin: run
  their server with `VAANI_AUTH__ENABLED=false`.
- The thread running `verify_google` cannot be cancelled; the timeout bounds it.
- `gateway.py` is now 344 lines and `config.py` 416, both over the ~300 limit.

## 7. Set up auth locally

1. Google Cloud Console, APIs & Services, Credentials: create an **OAuth client ID** of
   type "Web application". Under Authorized JavaScript origins add both
   `http://localhost` and `http://localhost:5173`. Copy the client ID.
2. In `backend/.env`: `VAANI_AUTH__GOOGLE_CLIENT_ID=` that ID, and the same value as
   `VITE_GOOGLE_CLIENT_ID` in `frontend/.env.local`.
3. Generate the secret and paste it as `VAANI_AUTH__SESSION_SECRET`:
   `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`.
4. `VAANI_AUTH__ALLOWED_EMAILS=["you@gmail.com"]`, a JSON list.
5. Open the app at `http://localhost:5173`, never `127.0.0.1`: they are different
   origins, and the cookie set for one is never sent to the other.
6. To work offline or run the measurement scripts: `VAANI_AUTH__ENABLED=false`.
