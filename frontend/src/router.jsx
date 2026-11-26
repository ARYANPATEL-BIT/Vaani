/**
 * Application router — defines every navigable route in Vaani.
 *
 * Uses react-router-dom's createBrowserRouter (a "data router"): a route can
 * have a loader, a function the router runs and waits for before it shows
 * the route. The table below is the full list of routes; it is not repeated
 * in this comment.
 *
 * Sign-in gate: / and /login are public. /talk and everything in the sidebar
 * layout run signedInOnly first (src/login/requireSignIn.js): a signed-out
 * visitor is sent to /login before the page is ever drawn.
 */

import { createBrowserRouter } from 'react-router-dom';
import { AUTH_CHECK_TIMEOUT_MS } from './config.js';
import { fetchVoice } from './api/studioApi.js';
import AppLayout from './components/AppLayout.jsx';
import StudioPage from './talk/StudioPage.jsx';
import LoginPage from './login/LoginPage.jsx';
import { NO_USER, requireSignIn } from './login/requireSignIn.js';
import LoopbackPage from './pages/LoopbackPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';
import VoiceStudioPage from './voice/VoiceStudioPage.jsx';

/**
 * The gate's loader. `request.signal` is aborted by the router if the
 * visitor navigates away before the check is done.
 * DEV only: /talk?preview=... is a design preview with no backend, so it
 * skips the check (in a production build this `if` is removed).
 */
function signedInOnly({ request }) {
  if (import.meta.env.DEV && new URL(request.url).searchParams.has('preview')) return NO_USER;
  return requireSignIn({ signal: request.signal, timeoutMs: AUTH_CHECK_TIMEOUT_MS });
}

// Drawn on the FIRST page load while the gate checks (one /auth/me call):
// the plain page background, so no gated page flashes before a redirect.
// Later navigations keep the previous page on screen while the loader runs.
const CHECKING = <div aria-busy="true" />;

const router = createBrowserRouter([
  // Landing page at "/": no sidebar. `lazy` loads it as a separate chunk,
  // so the voice app's pages never download the landing page's code.
  {
    path: '/',
    lazy: async () => ({ Component: (await import('./landing/LandingPage.jsx')).default }),
    // Shown while that chunk downloads: the page's black, not a white flash.
    hydrateFallbackElement: <div style={{ position: 'fixed', inset: 0, background: '#000' }} />,
  },
  // The conversation page ("Studio" design): it brings its own icon rail,
  // so it sits outside the sidebar layout below.
  { path: '/talk', element: <StudioPage />, loader: signedInOnly, hydrateFallbackElement: CHECKING },
  // Sign-in ("studio door" design): its own full-page layout, like /talk.
  { path: '/login', element: <LoginPage /> },
  {
    // No path: this route only wraps its children in the sidebar layout, and
    // gates all of them with one loader. Sidebar.jsx reads its answer.
    element: <AppLayout />,
    loader: signedInOnly,
    hydrateFallbackElement: CHECKING,
    children: [
      // Week 2 Day 5: loopback measurement rig (speaker → mic round-trip delay)
      { path: 'loopback', element: <LoopbackPage /> },
      // Phase 2 voice studio: enrol your own voice, hear a script in it.
      // Replaces the four /enrol pages (feat/voice-studio).
      // Its loader asks the studio whether this user's voice is enrolled.
      { path: 'voice', element: <VoiceStudioPage />, loader: () => fetchVoice() },
      // Future routes:
      // { path: 'profiles', lazy: () => import('./pages/ProfilesPage.jsx') },
      // { path: 'settings', lazy: () => import('./pages/SettingsPage.jsx') },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export default router;
