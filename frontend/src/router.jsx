/**
 * Application router — defines every navigable route in Vaani.
 *
 * Uses react-router-dom's createBrowserRouter for data-loading support
 * and future-proof navigation. Routes are defined declaratively so the
 * full route table is visible in one place.
 *
 * Today only two routes exist:
 *   /      → ConversationPage (the main voice interface)
 *   *      → NotFoundPage     (catch-all 404)
 *
 * Future routes (enrolment, profiles, settings) will be added here
 * as lazy-loaded imports when their pages are built.
 */

import { createBrowserRouter } from 'react-router-dom';
import AppLayout from './components/AppLayout.jsx';
import ConversationPage from './pages/ConversationPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <ConversationPage /> },
      // Future routes:
      // { path: 'enrol',    lazy: () => import('./pages/EnrolPage.jsx') },
      // { path: 'profiles', lazy: () => import('./pages/ProfilesPage.jsx') },
      // { path: 'settings', lazy: () => import('./pages/SettingsPage.jsx') },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export default router;
