# 01 — Frontend Setup and Contracts

## 1. In one minute

This establishes the React frontend under `frontend/` using Vite. It sets up
client-side routing with `react-router-dom`, a clean shell layout with the
initial `ConversationPage`, centralized audio configuration matching the
backend, production build and linting pipelines, and drafts the initial
audio and session contracts with Aryan in `docs/contracts.md`.

## 2. Files

| Path | What it is for |
|---|---|
| `frontend/package.json` | Project dependencies, scripts (`dev`, `build`, `lint`) |
| `frontend/vite.config.js` | Vite build tool configuration with React plugin |
| `frontend/eslint.config.js` | Flat ESLint config enforcing React Hooks & Refresh |
| `frontend/index.html` | HTML entry point mounting `<div id="root">` |
| `frontend/.env.example` | Template for environment variables (`VITE_API_BASE_URL`, `VITE_WS_URL`) |
| `frontend/src/main.jsx` | DOM entry point rendering `<App />` into StrictMode |
| `frontend/src/App.jsx` | Root component mounting `RouterProvider` |
| `frontend/src/router.jsx` | Central route table (`/`, 404, future placeholders) |
| `frontend/src/config.js` | Audio & endpoint settings (16 kHz, 20 ms, 320 samples) |
| `frontend/src/index.css` | Design tokens, CSS variables, and base resets |
| `frontend/src/components/AppLayout.jsx` | Persistent shell with header and `<Outlet />` |
| `frontend/src/components/AppLayout.css` | Header and layout container styling |
| `frontend/src/pages/ConversationPage.jsx` | Main voice UI shell with status panel |
| `frontend/src/pages/ConversationPage.css` | Status panel and typography styling |
| `frontend/src/pages/NotFoundPage.jsx` | Fallback 404 page with return link |
| `docs/contracts.md` | Agreed health check and proposed binary audio/session contract |

## 3. How it works

The frontend mounts as a Single Page Application (SPA).

```
index.html ──> main.jsx ──> App.jsx ──> router.jsx ──> AppLayout.jsx ──> ConversationPage.jsx
```

**Bootstrapping.** `index.html` loads `/src/main.jsx`. React creates a root on
`<div id="root">` and renders `<App />` inside `StrictMode`:

```jsx
// frontend/src/main.jsx
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

**Routing.** `App.jsx` renders `RouterProvider` using the declarative router
created in `src/router.jsx`:

```jsx
// frontend/src/router.jsx
const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <ConversationPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
```

`AppLayout` provides the persistent application header and uses `<Outlet />`
to render the active route:

```jsx
// frontend/src/components/AppLayout.jsx
export default function AppLayout() {
  return (
    <div className="app-layout">
      <header className="app-header">
        <Link to="/" className="app-logo">Vaani</Link>
      </header>
      <Outlet />
    </div>
  );
}
```

**Synchronized Audio Configuration.** Audio parameters in `src/config.js` match
`backend/config.toml` so both sides compute identical frame boundaries:

```javascript
// frontend/src/config.js
export const AUDIO_SAMPLE_RATE = 16_000;
export const AUDIO_FRAME_MS = 20;
export const AUDIO_FRAME_SAMPLES = AUDIO_SAMPLE_RATE * (AUDIO_FRAME_MS / 1000);
```

16,000 samples/sec × 0.020 sec = 320 samples per frame (640 bytes in Int16LE).

## 4. New concepts

- **Vite** — a fast frontend build tool and dev server. It serves native ES
  modules during development with near-instant Hot Module Replacement (HMR)
  and bundles with Rollup for production.
- **Client-Side Routing (`react-router-dom`)** — changing views in the browser
  by manipulating the URL history without requesting new HTML pages from the
  server.
- **`<Outlet />`** — a React Router component that acts as a placeholder where
  child route components are rendered inside a parent layout.
- **Audio Frame Size** — the chunk size processed at once. At 16 kHz, a 20 ms
  frame contains 320 mono samples. Int16 PCM requires 2 bytes per sample,
  yielding 640 bytes per WebSocket frame.

## 5. Why this and not that

| Choice | Picked | Alternatives | Why not them |
|---|---|---|---|
| Build tool | Vite | Next.js; Webpack | Next.js adds server-side Node rendering overhead unnecessary for client audio; Webpack is significantly slower to configure and run |
| Routing | `react-router-dom` v7 | Manual state routing; TanStack Router | Manual routing doesn't handle browser history/deep links; TanStack Router adds extra complexity for Day 1 requirements |
| Audio config | Mirrored `config.js` | Hardcoding in components; fetching config at runtime | Hardcoding leads to drift; fetching via HTTP adds latency and startup dependencies before audio capture can init |
| UI Styling | Vanilla CSS + CSS variables | Tailwind CSS; CSS-in-JS | Tailwind requires extra build tooling and was not requested; CSS-in-JS runtime overhead hurts audio frame performance |

## 6. When things go wrong

| What fails | What the code does |
|---|---|
| Unmatched URL path | Router matches `path: '*'` and renders `NotFoundPage` with return link |
| Missing env variable | Falls back to default `http://localhost:8000` or `ws://localhost:8000/ws/audio` |
| ESLint rule violation | `npm run lint` exits non-zero and prints offending file, line, and rule |
| Vite build syntax error | `npm run build` halts, prints bundle transform error, exits with code 1 |
| Backend unreachable | Day 1 UI indicates "Not connected"; future WS transport will surface retry/failure states |

## 7. Questions you could be asked

1. **Where is the entry point that mounts React to the DOM?**
   `frontend/src/main.jsx` calls `createRoot(document.getElementById('root')).render(...)`.
2. **Where is the application route table defined?**
   `frontend/src/router.jsx` exports `router` constructed via `createBrowserRouter`.
3. **Where are the audio parameters defined, and how do they relate to the backend?**
   `frontend/src/config.js` exports `AUDIO_SAMPLE_RATE` (16,000) and `AUDIO_FRAME_MS` (20),
   mirroring `[audio]` in `backend/config.toml`.
4. **What happens if a user navigates to `/unknown`?**
   `router.jsx` catches it with `{ path: '*', element: <NotFoundPage /> }`, displaying a
   clean 404 message and a link back to `/`.
5. **Why not hardcode `http://localhost:8000` directly in fetch calls?**
   Hardcoding breaks production deployment and staging environments. We read
   `import.meta.env.VITE_API_BASE_URL` with a local fallback.
6. **Why Int16LE rather than Float32 for audio frames in `docs/contracts.md`?**
   Float32 uses 4 bytes per sample (1280 bytes/frame). Int16LE uses 2 bytes
   (640 bytes/frame), halving WebSocket payload bandwidth, and directly matches
   what Silero VAD and Whisper accept.
7. **What is the purpose of `AppLayout.jsx`?**
   It wraps pages in a shared header while delegating content rendering to `<Outlet />`,
   preventing header re-renders on route changes.
8. **(Hardest) Why did we use `createBrowserRouter` instead of `<BrowserRouter>` with inline `<Routes>`?**
   `createBrowserRouter` decouples the route configuration from the UI tree, enabling
   route-level data loaders, error boundaries, and code-split lazy loading (`lazy: () => import(...)`)
   without nesting route components in JSX.

## 8. Check yourself

Answer out loud, document closed:

1. Trace the execution path from `index.html` to rendering `ConversationPage`.
2. How many bytes are in a 20 ms mono audio frame at 16 kHz in 16-bit PCM?
3. Which contract decisions are agreed, and which are pending Aryan's confirmation?
