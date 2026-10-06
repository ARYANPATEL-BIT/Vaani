/**
 * WaveformHero — Flowing sine-wave visual driven by turnState.
 *
 * Uses SVG animated paths for the iridescent ribbon look.
 * In idle state: calm flat line with minimal motion.
 * In active states: multi-layered flowing ribbons with varying amplitude.
 * Equalizer bars fade at both edges.
 */

import { useMemo } from 'react';
import './WaveformHero.css';

const STATE_HEADING = {
  idle:       'Ready',
  listening:  'Listening…',
  thinking:   'Thinking…',
  speaking:   'Speaking…',
  cancelling: 'Resetting…',
  disconnected: 'Ready',
  error:      'Connection Issue',
};

const STATE_SUBTITLE = {
  idle:        'Vaani is ready',
  listening:   "Go ahead, I'm listening",
  thinking:    'Processing your message',
  speaking:    'Vaani is responding',
  cancelling:  'Resetting turn state',
  disconnected: 'Connect to start talking',
  error:       'Please retry the connection',
};

export default function WaveformHero({ turnState = 'idle', isConnected = false }) {
  const effectiveState = isConnected ? turnState : (turnState === 'idle' ? 'disconnected' : turnState);
  const heading  = STATE_HEADING[effectiveState]  || 'Ready';
  const subtitle = STATE_SUBTITLE[effectiveState] || '';

  // Number of equalizer bars
  const eqBars = useMemo(() => Array.from({ length: 32 }, (_, i) => i), []);

  return (
    <div className={`waveform-hero state-${turnState}`} aria-hidden="false">
      {/* SVG Waveform Area */}
      <div className="waveform-svg-area" aria-hidden="true">

        {/* Left + Right EQ bars */}
        <div className="eq-bars eq-left">
          {eqBars.slice(0, 16).map(i => (
            <div key={i} className="eq-bar" style={{ '--delay': `${i * 0.04}s`, '--base-h': `${Math.max(3, Math.abs(8 - i) * 3 + 4)}px` }} />
          ))}
        </div>
        <div className="eq-bars eq-right">
          {eqBars.slice(16).map(i => (
            <div key={i} className="eq-bar" style={{ '--delay': `${(i - 16) * 0.04}s`, '--base-h': `${Math.max(3, (i - 16) * 3 + 4)}px` }} />
          ))}
        </div>

        {/* SVG flowing ribbons */}
        <svg
          className="wave-svg"
          viewBox="0 0 800 140"
          preserveAspectRatio="xMidYMid meet"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="wave-grad-1" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%"   stopColor="#60A5FA" stopOpacity="0" />
              <stop offset="20%"  stopColor="#60A5FA" stopOpacity="0.7" />
              <stop offset="50%"  stopColor="#8B5CF6" stopOpacity="0.9" />
              <stop offset="80%"  stopColor="#EC4899" stopOpacity="0.7" />
              <stop offset="100%" stopColor="#EC4899" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="wave-grad-2" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%"   stopColor="#818CF8" stopOpacity="0" />
              <stop offset="25%"  stopColor="#818CF8" stopOpacity="0.6" />
              <stop offset="60%"  stopColor="#C084FC" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#C084FC" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="wave-grad-3" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%"   stopColor="#38BDF8" stopOpacity="0" />
              <stop offset="30%"  stopColor="#38BDF8" stopOpacity="0.5" />
              <stop offset="70%"  stopColor="#A78BFA" stopOpacity="0.65" />
              <stop offset="100%" stopColor="#A78BFA" stopOpacity="0" />
            </linearGradient>
            <filter id="wave-blur">
              <feGaussianBlur stdDeviation="1.5" />
            </filter>
          </defs>

          {/* Glow layer (blurred) */}
          <path className="wave-path wave-glow wave-1" stroke="url(#wave-grad-1)" strokeWidth="6" fill="none" filter="url(#wave-blur)" />

          {/* Main ribbon layers */}
          <path className="wave-path wave-1" stroke="url(#wave-grad-1)" strokeWidth="2.5" fill="none" />
          <path className="wave-path wave-2" stroke="url(#wave-grad-2)" strokeWidth="2" fill="none" />
          <path className="wave-path wave-3" stroke="url(#wave-grad-3)" strokeWidth="1.8" fill="none" />
        </svg>
      </div>

      {/* State heading */}
      <div className="waveform-labels">
        <h2 className="state-heading">{heading}</h2>
        <p className="state-subtitle">{subtitle}</p>
      </div>
    </div>
  );
}
