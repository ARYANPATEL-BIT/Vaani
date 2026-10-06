/**
 * AppShell — 3-column grid layout + theme toggling.
 * Grid: sidebar | main-stage | right-panel
 */

import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar.jsx';
import './AppLayout.css';

export default function AppLayout() {
  const [theme, setTheme] = useState(() => localStorage.getItem('vaani-theme') || 'light');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('vaani-theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark');

  return (
    <div className="app-shell">
      <Sidebar />
      <Outlet context={{ theme, toggleTheme }} />
    </div>
  );
}
