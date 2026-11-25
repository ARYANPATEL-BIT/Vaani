/**
 * RailNav -- the Studio's 72 px icon rail (desktop and tablet; hidden on a
 * phone, where the Ink toggle lives in the settings sheet instead).
 *
 * Every item of the old sidebar that is visible today is here: Talk
 * (was "Conversation"), History (disabled), the theme toggle (here "Ink
 * mode") and the operator avatar. Sign out (feat/login-page) posts
 * /auth/logout and opens /login (src/login/useSignOut.js).
 */

import { Link, NavLink } from 'react-router-dom';
import { History, LogOut, Mic, Moon, Sun } from 'lucide-react';
import useSignOut from '../login/useSignOut.js';
import { TEXT } from './talkContent.js';
import { VaaniIcon } from '../components/brand/VaaniLogo.jsx';

const ICON = 20; // px, lucide takes a number

export default function RailNav({ ink, onToggleInk }) {
  const inkLabel = ink ? TEXT.rail.paper : TEXT.rail.ink;
  const signOut = useSignOut();
  return (
    <nav className="tk-rail" aria-label={TEXT.rail.nav}>
      <Link to="/" className="tk-rail-mark" aria-label={TEXT.rail.home}>
        <VaaniIcon size={28} ink="var(--tk-text)" paper="var(--tk-bg)" />
      </Link>
      <div className="tk-rail-group">
        {/* NavLink adds aria-current="page" when /talk is open. */}
        <NavLink to="/talk" className="tk-rail-btn" aria-label={TEXT.rail.talk} title={TEXT.rail.talk}>
          <Mic size={ICON} strokeWidth={1.8} aria-hidden="true" />
        </NavLink>
        {/* aria-disabled, not disabled: it stays focusable, so a keyboard
            or screen-reader user can still find out what it is. */}
        <button type="button" className="tk-rail-btn" aria-disabled="true"
          aria-label={TEXT.rail.history} title={TEXT.rail.history}>
          <History size={ICON} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
      <div className="tk-rail-group tk-rail-foot">
        {/* The label names what a click does, like the old sidebar toggle. */}
        <button type="button" className="tk-rail-btn" aria-label={inkLabel} title={inkLabel} onClick={onToggleInk}>
          {ink
            ? <Sun size={ICON} strokeWidth={1.8} aria-hidden="true" />
            : <Moon size={ICON} strokeWidth={1.8} aria-hidden="true" />}
        </button>
        <button type="button" className="tk-rail-btn" aria-label={TEXT.rail.signOut} title={TEXT.rail.signOut} onClick={signOut}>
          <LogOut size={ICON} strokeWidth={1.8} aria-hidden="true" />
        </button>
        <span className="tk-mono tk-avatar" role="img" aria-label={TEXT.rail.operator} title={TEXT.rail.operator}>A</span>
      </div>
    </nav>
  );
}
