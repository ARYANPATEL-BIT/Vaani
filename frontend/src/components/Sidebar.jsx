/**
 * Sidebar — Left navigation rail with logo, nav items, theme toggle,
 * operator row & logout.
 */

import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Mic, Video, History, User, BarChart2, Settings,
  ChevronRight, LogOut, UserCheck, Moon, Sun
} from 'lucide-react';
import { applyTheme, saveTheme } from '../theme/theme.js';
import './AppLayout.css';

// Width of the sidebar's icon column in px. Every row (nav and footer) uses
// it, and .operator-avatar in AppLayout.css matches it, so all the icons sit
// in one vertical line. lucide takes the size as a px number.
const ICON_SIZE = 20;

// hidden: true keeps an item out of the sidebar only. Its route and page
// still exist, so /loopback and /enrol/* still open when typed as a URL.
// Remove the flag to bring an item back.
const NAV_ITEMS = [
  { to: '/', label: 'Conversation', icon: Mic, end: true },
  { to: '/loopback', label: 'Studio', icon: Video, hidden: true },
  // Week 3 Day 3: enrolment screens
  { to: '/enrol', label: 'Enrol', icon: UserCheck, hidden: true },
  { to: '/history', label: 'History', icon: History, disabled: true },
  { to: '/identity', label: 'Identity', icon: User, disabled: true, hidden: true },
  { to: '/spend', label: 'Spend & Quota', icon: BarChart2, disabled: true, hidden: true },
  { to: '/settings', label: 'Settings', icon: Settings, disabled: true, hidden: true },
];

const VISIBLE_NAV_ITEMS = NAV_ITEMS.filter((item) => !item.hidden);

export default function Sidebar() {
  // The inline script in index.html already chose the theme and set it on
  // <html> before React loaded, so start from what it chose.
  const [theme, setTheme] = useState(
    () => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'),
  );

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark';
    applyTheme(next, document.documentElement); // CSS recolours everything
    saveTheme(next, () => window.localStorage); // remembered for next visit
    setTheme(next); // only this button's icon and label re-render
  }

  const toggleLabel = theme === 'dark' ? 'Light mode' : 'Dark mode';

  return (
    <aside className="sidebar">
      {/* Logo */}
      <NavLink to="/" className="sidebar-logo">
        <div className="logo-icon" aria-hidden="true">
          {[1,2,3,4,5].map(i => <div key={i} className="logo-bar" />)}
        </div>
        <span className="logo-wordmark">Vaani</span>
      </NavLink>

      {/* Navigation */}
      <nav className="sidebar-nav" aria-label="Main navigation">
        {VISIBLE_NAV_ITEMS.map(({ to, label, icon: Icon, end, disabled }) =>
          disabled ? (
            <div key={label} className="nav-item" style={{ opacity: 0.45, cursor: 'default' }}>
              <Icon size={ICON_SIZE} strokeWidth={1.8} />
              <span>{label}</span>
            </div>
          ) : (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Icon size={ICON_SIZE} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          )
        )}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        {/* The label names what a click does: "Dark mode" in light, "Light
            mode" in dark. No aria-pressed: a label that changes AND a pressed
            state would tell a screen reader two different things. aria-label
            and title repeat the text for the collapsed, icon-only rail. */}
        <button
          type="button"
          className="sidebar-theme-toggle"
          aria-label={toggleLabel}
          title={toggleLabel}
          onClick={toggleTheme}
        >
          {theme === 'dark'
            ? <Sun size={ICON_SIZE} strokeWidth={1.8} aria-hidden="true" />
            : <Moon size={ICON_SIZE} strokeWidth={1.8} aria-hidden="true" />}
          <span>{toggleLabel}</span>
        </button>
        <div className="operator-row">
          <div className="operator-avatar">A</div>
          <span className="operator-name">Operator</span>
          <ChevronRight className="operator-chevron" size={16} strokeWidth={2} color="var(--c-muted)" />
        </div>
        <div className="sidebar-logout">
          <LogOut size={ICON_SIZE} strokeWidth={1.8} />
          <span>Logout</span>
        </div>
      </div>
    </aside>
  );
}
