/**
 * TopBar — "Conversation" title + live badge, model pill, dark-mode toggle.
 */

import { Moon, Sun, Sparkles, ChevronDown } from 'lucide-react';
import './TopBar.css';

export default function TopBar({ wsStatus, theme, toggleTheme }) {
  const isLive  = wsStatus === 'ready';
  const isError = wsStatus === 'error';

  const pillLabel = isLive ? 'Live'
    : wsStatus === 'connecting' || wsStatus === 'connected' ? 'Connecting…'
    : isError ? 'Error'
    : 'Disconnected';

  const pillClass = isLive ? 'live-pill live'
    : isError ? 'live-pill error'
    : 'live-pill disconnected';

  return (
    <header className="topbar">
      <div className="topbar-left">
        <h1 className="topbar-title">Conversation</h1>
        <span className={pillClass}>
          <span className="live-dot" />
          {pillLabel}
        </span>
      </div>

      <div className="topbar-right">
        {/* Model / quota pill — clearly marked mock */}
        <div className="model-pill" title="Model provider (display only)">
          <Sparkles size={13} strokeWidth={2} style={{ color: 'var(--c-indigo)' }} />
          <span>Gemini</span>
          <span className="model-quota">· 82% left</span>
          <ChevronDown size={13} strokeWidth={2.5} />
        </div>

        {/* Dark / light theme toggle */}
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
        >
          {theme === 'dark'
            ? <Sun size={16} strokeWidth={2} />
            : <Moon size={16} strokeWidth={2} />}
        </button>
      </div>
    </header>
  );
}
