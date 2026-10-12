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
import ConversationPage from './pages/ConversationPage.jsx';
import EnrolConsentPage from './pages/EnrolConsentPage.jsx';
import EnrolRecordPage from './pages/EnrolRecordPage.jsx';
import EnrolValidationPage from './pages/EnrolValidationPage.jsx';
import LoopbackPage from './pages/LoopbackPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <ConversationPage /> },
      // Week 2 Day 5: loopback measurement rig (speaker → mic round-trip delay)
      { path: 'loopback', element: <LoopbackPage /> },
      // Week 3 Day 3: enrolment — consent + reference voice recording
      { path: 'enrol', element: <EnrolConsentPage /> },
      { path: 'enrol/record', element: <EnrolRecordPage /> },
      // Week 3 Day 5: enrolment validation feedback
      { path: 'enrol/validation', element: <EnrolValidationPage /> },
      // Future routes:
      // { path: 'profiles', lazy: () => import('./pages/ProfilesPage.jsx') },
      // { path: 'settings', lazy: () => import('./pages/SettingsPage.jsx') },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export default router;
