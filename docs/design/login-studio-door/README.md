# Login: "studio door" design

The `/login` page's design. Built in `frontend/src/login/` (branch `feat/login-page`).

Each state is one `.dc.html` mockup (open it in a browser) with a `.png` of how it looks:

| File | State | Shown when |
|---|---|---|
| `LoginOff` | Signed out | First visit; `GET /auth/me` answered 401 |
| `LoginChecking` | Checking | Google returned an ID token; `POST /auth/google` is in flight |
| `LoginRefused` | Not on the list | `POST /auth/google` answered 403 `AUTH_NOT_ALLOWED` |
| `LoginError` | Google unreachable | `POST /auth/google` answered 503 `AUTH_UNAVAILABLE` |
| `LoginOnAir` | Signed in | `POST /auth/google` answered 200; `/talk` opens 1.5 s later |
| `LoginPhone` | Signed out, 390 px | The stacked phone layout |

Where the build differs from the mockups, on purpose:

- The white "Sign in with Google" button in the mockups is a stand-in. The page shows Google's
  own button (Google Identity Services, outline theme, pill shape), which we cannot restyle.
  "Use another account" and "Try again" are that same button: the alert above it says what
  happened.
- The mockups load Archivo from Google Fonts, where the condensed width did not apply. The page
  uses the self-hosted condensed Archivo that the landing page and `/talk` use, so its type is
  narrower than in the `.png` files.
- More answers than the mockups show get an alert (unverified email, rejected token, bad origin,
  server not answering); wording in `frontend/src/login/loginContent.js` (`ALERTS`).

Every state can be checked in development without Google or a backend:
`/login?preview=off|checking|refused|error|onair`.
