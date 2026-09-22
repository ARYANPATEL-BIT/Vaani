/**
 * AppLayout — the persistent shell that wraps every page.
 *
 * Contains the application header and renders the active page
 * via react-router's <Outlet />. Shared UI elements (nav bar,
 * global error boundary, etc.) will live here as they are built.
 */

import { Outlet, Link } from 'react-router-dom';
import './AppLayout.css';

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
