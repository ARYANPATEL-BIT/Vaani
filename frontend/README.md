# Vaani — Frontend

React application for real-time voice conversation in Hindi, English,
and Hinglish. Built with Vite.

## Requirements

- **Node.js 20.19+, 22.13+ or 24+**: what vite 8.3.0 and eslint 10.11.0,
  pinned in `package-lock.json`, require
- **npm** (ships with Node)

## Getting started

```bash
cd frontend

# Install dependencies (first time, or after package.json changes).
npm install

# Start the development server with hot module replacement.
npm run dev
```

The dev server runs at http://localhost:5173 by default.

## Available scripts

| Command           | What it does                              |
|-------------------|-------------------------------------------|
| `npm run dev`     | Start Vite dev server with HMR            |
| `npm run build`   | Production build to `dist/`               |
| `npm run preview` | Serve the production build locally        |
| `npm run lint`    | Run ESLint across all source files        |

## Environment variables

Copy `.env.example` to `.env.local` and adjust as needed:

```bash
cp .env.example .env.local
```

| Variable                | Default                 | Purpose |
|-------------------------|-------------------------|---------|
| `VAANI_PROXY_TARGET`    | `http://localhost:8000` | Where the dev server's proxy forwards `/auth`, `/health` and `/ws` (read by `vite.config.js` only, never sent to the browser) |
| `VITE_GOOGLE_CLIENT_ID` | empty                   | Google OAuth client ID for the `/login` button; same value as the backend's `VAANI_AUTH__GOOGLE_CLIENT_ID` |

The page and the backend share one origin. The browser calls relative URLs
(`/auth/me`, `ws://<page host>/ws/session`) and the Vite dev server (and
`npm run preview`) proxies them to the backend, so the session cookie works
locally and through a Cloudflare tunnel. Open the app at
`http://localhost:5173`, not `127.0.0.1`: the backend's `[auth]
allowed_origins` lists `http://localhost:5173`.

## Project structure

```
src/
├── main.jsx              # Entry point — mounts RouterProvider
├── router.jsx            # All application routes
├── config.js             # Centralised configuration
├── index.css             # Global styles and CSS variables
├── components/
│   └── AppLayout.jsx     # Persistent page shell (header + Outlet)
├── landing/              # The landing page
├── api/                  # authApi.js (sign-in calls), enrolApi.js
├── login/                # /login (Google sign-in), the route gate (requireSignIn.js), sign out
├── talk/
│   └── StudioPage.jsx    # The conversation page
└── pages/
    └── NotFoundPage.jsx       # 404 catch-all
```

## Routing

Routes are defined in `src/router.jsx` using react-router-dom v7.

| Path           | Page             | What it is                                  |
|----------------|------------------|---------------------------------------------|
| `/`            | LandingPage      | The landing page                            |
| `/talk`        | StudioPage       | The voice conversation, outside the sidebar layout |
| `/login`       | LoginPage        | Sign in with Google ("studio door"), outside the sidebar layout |
| `/loopback`    | LoopbackPage     | Loopback rig: speaker-to-mic delay          |
| `/enrol`       | EnrolConsentPage | Enrolment: consent before recording         |
| `/enrol/record`| EnrolRecordPage  | Enrolment: record the reference voice       |
| `*`            | NotFoundPage     | 404 catch-all                               |

`/loopback`, the `/enrol` pages and the `*` catch-all (NotFoundPage) are children of `AppLayout` (the sidebar layout); `/` (LandingPage), `/talk` (StudioPage) and `/login` (LoginPage) are top-level routes with their own layouts.

Sign-in gate: `/talk` and the whole sidebar layout have a loader (`src/login/requireSignIn.js`) that asks `GET /auth/me` before the page is drawn; a 401 goes to `/login`. `/` and `/login` are public. With `[auth] enabled=false` on the backend, everyone is let in and the sidebar shows "Operator".

In development, `/login?preview=off|checking|refused|error|onair` shows each sign-in state without a backend or a Google client ID (`src/login/loginPreview.js`). Real sign-in needs `VITE_GOOGLE_CLIENT_ID` in `frontend/.env.local`, the same ID as the backend's `VAANI_AUTH__GOOGLE_CLIENT_ID`.

Future routes (profiles, settings) are commented in the router and will
be added as lazy-loaded imports.
