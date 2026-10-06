/**
 * ControlDock — Fixed floating bottom bar with keyboard shortcuts.
 *
 * Center: large glowing mic button (Start/Stop session).
 * Left:   Mute (Ctrl+M), Interrupt (Space).
 * Right:  Type instead (Ctrl+K), Transcript (Ctrl+T).
 * Far right: End session pill (Ctrl+E).
 *
 * Keyboard shortcuts are implemented via useEffect.
 */

import { useEffect } from 'react';
import {
  MicOff, Square, Keyboard, FileText, PhoneOff, Mic
} from 'lucide-react';
import './ControlDock.css';

function DockAction({ icon: Icon, label, shortcut, onClick, disabled, danger }) {
  return (
    <button
      className={`dock-action${danger ? ' danger' : ''}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={`${label} (${shortcut})`}
      title={`${label} — ${shortcut}`}
    >
      <Icon size={20} strokeWidth={1.8} />
      <span className="dock-action-label">{label}</span>
      <span className="dock-shortcut">{shortcut}</span>
    </button>
  );
}

export default function ControlDock({
  isCapturing,
  isTransitioning,
  onConnect,
  onDisconnect,
  onMute,   // placeholder, not yet implemented in backend
}) {
  // Keyboard shortcuts
  useEffect(() => {
    function handler(e) {
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;

      if (e.ctrlKey && e.key === 'm') {
        e.preventDefault();
        onMute?.();
      }
      if (e.ctrlKey && e.key === 'e') {
        e.preventDefault();
        if (isCapturing) onDisconnect();
      }
      if (e.code === 'Space' && !e.ctrlKey && !e.shiftKey && !e.altKey) {
        // Only trigger if not focused on a button (would double-fire)
        if (document.activeElement?.tagName !== 'BUTTON') {
          e.preventDefault();
          if (!isCapturing && !isTransitioning) onConnect();
          else if (isCapturing) onDisconnect();
        }
      }
    }
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isCapturing, isTransitioning, onConnect, onDisconnect, onMute]);

  return (
    <div className="control-dock-wrap" role="toolbar" aria-label="Voice controls">
      <div className="control-dock">
        {/* Left actions */}
        <div className="dock-group">
          <DockAction icon={MicOff}   label="Mute"      shortcut="Ctrl + M" onClick={onMute} disabled={!isCapturing} />
          <DockAction icon={Square}   label="Interrupt"  shortcut="Space"   onClick={null} disabled title="Not yet supported" />
        </div>

        <div className="dock-divider" />

        {/* Center: primary mic button */}
        <button
          id={isCapturing ? 'disconnect-btn' : 'connect-btn'}
          className={`mic-btn${isCapturing ? ' active' : ''}${isTransitioning ? ' loading' : ''}`}
          onClick={isCapturing ? onDisconnect : onConnect}
          disabled={isTransitioning}
          aria-label={isCapturing ? 'End conversation' : 'Start conversation'}
        >
          <div className="mic-btn-halo" />
          <Mic size={28} strokeWidth={1.8} />
        </button>

        <div className="dock-divider" />

        {/* Right actions */}
        <div className="dock-group">
          <DockAction icon={Keyboard}  label="Type instead" shortcut="Ctrl + K" onClick={null} disabled title="Not yet supported" />
          <DockAction icon={FileText}  label="Transcript"   shortcut="Ctrl + T" onClick={null} disabled title="Not yet supported" />
        </div>

        <div className="dock-divider tall" />

        {/* End session pill */}
        <button
          className="end-session-btn"
          onClick={isCapturing ? onDisconnect : null}
          disabled={!isCapturing}
          aria-label="End session (Ctrl+E)"
          title="End session — Ctrl + E"
        >
          <PhoneOff size={16} strokeWidth={2} />
          <span>End session</span>
          <span className="end-shortcut">Ctrl + E</span>
        </button>
      </div>
    </div>
  );
}
