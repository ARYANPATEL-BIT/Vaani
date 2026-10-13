/**
 * VoiceOrb — visual voice presence indicator for Vaani.
 *
 * Implements the iridescent voice orb target visual:
 * - Fluid iridescent sphere with inner glow, specular reflections, and aura
 * - Ambient horizontal wave ribbons
 * - State title ("Listening...", "Thinking...", "Speaking...", "Ready")
 * - Subtitle guidance
 * - Sound wave equalizer bars underneath
 *
 * Reflects genuine backend turn states:
 *   idle | listening | thinking | speaking | cancelling
 */

import { useMemo } from 'react';
import './VoiceOrb.css';

const STATE_CONFIG = {
  // Connected and idle. "Tap connect" belongs only to the disconnected orb.
  idle: {
    title: 'Ready',
    subtitle: 'Start speaking whenever you like',
    badge: 'Idle',
  },
  listening: {
    title: 'Listening...',
    subtitle: "Go ahead, I'm listening",
    badge: 'Listening',
  },
  thinking: {
    title: 'Thinking...',
    subtitle: 'Processing your question',
    badge: 'Thinking',
  },
  speaking: {
    title: 'Speaking...',
    subtitle: 'Vaani is speaking',
    badge: 'Speaking',
  },
  cancelling: {
    title: 'Interrupted',
    subtitle: 'Turn was interrupted',
    badge: 'Interrupted',
  },
};

// Push-to-talk (contracts.md 2.8): the user's presses, not silence, end a
// turn, so the two states the user acts in say which control to use.
const PTT_SUBTITLES = {
  idle: 'Press Speak, or hold Space, to talk',
  listening: "Press Stop, or let go of Space, when you're done",
};

export function VoiceOrb({
  turnState = 'idle',
  isConnected = false,
  isTransitioning = false,
  errorMessage = null,
  onClick = null,
  mode = 'vad', // the session's input mode: 'vad' | 'ptt'
}) {
  // Determine effective state
  const effectiveState = useMemo(() => {
    if (errorMessage) return 'error';
    if (!isConnected) return 'disconnected';
    return turnState || 'idle';
  }, [errorMessage, isConnected, turnState]);

  const displayMeta = useMemo(() => {
    if (errorMessage) {
      return {
        title: 'Connection Issue',
        subtitle: 'Please check your connection and retry',
      };
    }
    if (!isConnected) {
      if (isTransitioning) {
        return {
          title: 'Connecting...',
          subtitle: 'Establishing secure voice session',
        };
      }
      return {
        title: 'Ready',
        subtitle: 'Tap connect to start conversation',
      };
    }
    const meta = STATE_CONFIG[turnState] || STATE_CONFIG.idle;
    if (mode === 'ptt' && PTT_SUBTITLES[turnState]) {
      return { ...meta, subtitle: PTT_SUBTITLES[turnState] };
    }
    return meta;
  }, [errorMessage, isConnected, isTransitioning, turnState, mode]);

  // Generate 24 equalizer bar elements with varying animation delays
  const equalizerBars = useMemo(() => {
    return Array.from({ length: 24 }).map((_, i) => {
      // Create symmetrical heights centered around middle
      const distFromCenter = Math.abs(i - 11.5) / 12;
      const baseScale = Math.max(0.2, 1 - distFromCenter * 0.7);
      return { id: i, baseScale, delay: (i * 0.06).toFixed(2) };
    });
  }, []);

  return (
    <div className={`voice-orb-container state-${effectiveState}`} data-testid="voice-orb-container">
      {/* Background ambient wave ribbons */}
      <div className="orb-ambient-waves" aria-hidden="true">
        <svg className="wave-svg" viewBox="0 0 1000 240" fill="none" preserveAspectRatio="none">
          <path
            className="wave-ribbon wave-1"
            d="M0,120 C180,70 320,170 500,120 C680,70 820,165 1000,120 L1000,120 L0,120 Z"
          />
          <path
            className="wave-ribbon wave-2"
            d="M0,125 C160,165 340,75 500,125 C660,175 840,80 1000,125 L1000,125 L0,125 Z"
          />
          <path
            className="wave-ribbon wave-3"
            d="M0,120 C220,140 380,95 500,120 C620,145 780,100 1000,120 L1000,120 L0,120 Z"
          />
        </svg>
      </div>

      {/* Central Voice Orb Presence */}
      <div
        className="orb-stage"
        onClick={onClick}
        role={onClick ? 'button' : undefined}
        tabIndex={onClick ? 0 : undefined}
        aria-label={`Voice status: ${displayMeta.title}`}
      >
        <div className="orb-halo-outer" />
        <div className="orb-halo-middle" />

        <div className="orb-sphere">
          {/* Internal gradients & reflections */}
          <div className="orb-core" />
          <div className="orb-aurora-sweep" />
          <div className="orb-specular-highlight" />
          <div className="orb-rim-glow" />
        </div>
      </div>

      {/* Turn state title and subtitle */}
      <div className="orb-label-group">
        <h2 className="orb-title" id="orb-state-title">
          {displayMeta.title}
        </h2>
        <p className="orb-subtitle" id="orb-state-subtitle">
          {displayMeta.subtitle}
        </p>
      </div>

      {/* Audio-reactive equalizer bars */}
      <div className="orb-equalizer" aria-hidden="true">
        {equalizerBars.map((bar) => (
          <span
            key={bar.id}
            className="equalizer-bar"
            style={{
              '--bar-scale': bar.baseScale,
              '--bar-delay': `${bar.delay}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export default VoiceOrb;
