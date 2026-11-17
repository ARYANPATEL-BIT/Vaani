/**
 * Application router — defines every navigable route in Vaani.
 *
 * Uses react-router-dom's createBrowserRouter for data-loading support
 * and future-proof navigation. Routes are defined declaratively so the
 * full route table is visible in one place. The table below is the full
 * list of routes; it is not repeated in this comment.
 *
 * Future routes (profiles, settings) will be added here
 * as lazy-loaded imports when their pages are built.
 */

import { createBrowserRouter } from 'react-router-dom';
import AppLayout from './components/AppLayout.jsx';
import StudioPage from './talk/StudioPage.jsx';
import LoginPage from './login/LoginPage.jsx';
import RequireSignIn from './login/RequireSignIn.jsx';
import EnrolConsentPage from './pages/EnrolConsentPage.jsx';
import EnrolRecordPage from './pages/EnrolRecordPage.jsx';
import EnrolValidationPage from './pages/EnrolValidationPage.jsx';
import EnrolVerifyPage from './pages/EnrolVerifyPage.jsx';
import LoopbackPage from './pages/LoopbackPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';

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
  // so it sits outside the sidebar layout below. RequireSignIn draws it at
  // once and sends a signed-out visitor to /login (src/login/).
  { path: '/talk', element: <RequireSignIn><StudioPage /></RequireSignIn> },
  // Sign-in ("studio door" design): its own full-page layout, like /talk.
  { path: '/login', element: <LoginPage /> },
  {
    // No path: this route only wraps its children in the sidebar layout.
    element: <AppLayout />,
    children: [
      // Week 2 Day 5: loopback measurement rig (speaker → mic round-trip delay)
      { path: 'loopback', element: <LoopbackPage /> },
      // Week 3 Day 3: enrolment — consent + reference voice recording
      { path: 'enrol', element: <EnrolConsentPage /> },
      { path: 'enrol/record', element: <EnrolRecordPage /> },
      // Week 3 Day 5: enrolment validation feedback
      { path: 'enrol/validation', element: <EnrolValidationPage /> },
      // Week 4 Tuesday: hear the cloned voice, approve it or record again
      { path: 'enrol/verify', element: <EnrolVerifyPage /> },
      // Future routes:
      // { path: 'profiles', lazy: () => import('./pages/ProfilesPage.jsx') },
      // { path: 'settings', lazy: () => import('./pages/SettingsPage.jsx') },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export default router;
