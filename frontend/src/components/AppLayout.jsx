/**
 * AppShell — the page layout: sidebar | .app-main (the page, which scrolls
 * on its own). The light/dark toggle lives in Sidebar.jsx.
 */

import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar.jsx';
import './AppLayout.css';

export default function AppLayout() {
  return (
    <div className="app-shell">
      <Sidebar />
      {/* The scroll container for every page: the column right of the sidebar. */}
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
