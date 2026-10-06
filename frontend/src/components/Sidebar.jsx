/**
 * Sidebar — Left navigation rail with logo, nav items, operator row & logout.
 */

import { NavLink } from 'react-router-dom';
import {
  Mic, Video, History, User, BarChart2, Settings,
  ChevronRight, LogOut
} from 'lucide-react';
import './AppLayout.css';

const NAV_ITEMS = [
  { to: '/', label: 'Conversation', icon: Mic, end: true },
  { to: '/loopback', label: 'Studio', icon: Video },
  { to: '/history', label: 'History', icon: History, disabled: true },
  { to: '/identity', label: 'Identity', icon: User, disabled: true },
  { to: '/spend', label: 'Spend & Quota', icon: BarChart2, disabled: true },
  { to: '/settings', label: 'Settings', icon: Settings, disabled: true },
];

export default function Sidebar() {
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
        {NAV_ITEMS.map(({ to, label, icon: Icon, end, disabled }) =>
          disabled ? (
            <div key={label} className="nav-item" style={{ opacity: 0.45, cursor: 'default' }}>
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </div>
          ) : (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          )
        )}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="operator-row">
          <div className="operator-avatar">A</div>
          <span className="operator-name">Operator</span>
          <ChevronRight size={14} strokeWidth={2} color="var(--c-muted)" />
        </div>
        <div className="sidebar-logout">
          <LogOut size={16} strokeWidth={1.8} />
          <span>Logout</span>
        </div>
      </div>
    </aside>
  );
}
