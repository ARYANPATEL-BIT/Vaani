/**
 * StudioPage -- the /talk conversation page, "Studio" design.
 *
 * A VISUAL rewrite of the old ConversationPage. The conversation itself is
 * unchanged: the same hooks, and the same four handlers (handleServerMessage,
 * handleConnect, handleSpeak, handleDisconnect) and reset effect, with the
 * same statements in the same order (comments shortened). handleConnect
 * passes onServerMessage, which runs handleServerMessage first. The page
 * only READS what the hooks expose.
 *
 * Studio additions, all on the page side:
 * - onServerMessage: calls handleServerMessage first, unchanged, then notes
 *   the session start time, barge-ins (for CUT) and telemetry.
 * - the tape (useStudioTape.js), fed by readMicLevel / readPlaybackLevel.
 * - DEV only: ?preview=listening|thinking|speaking|cut (studioPreview.js).
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAudioCapture } from '../hooks/useAudioCapture.js';
import { usePlaybackQueue } from '../hooks/usePlaybackQueue.js';
import { useTranscript } from '../hooks/useTranscript.js';
import { useTurnState } from '../hooks/useTurnState.js';
import { useLatencyTelemetry } from '../hooks/useLatencyTelemetry.js';
import useReducedMotion from '../landing/useReducedMotion.js';
import { applyTheme, saveTheme } from '../theme/theme.js';
import { INK, PAPER, TAPE, TEXT, VIEWS } from './talkContent.js';
import { viewFor, isCutMessage, cutStillLatched, timecode } from './studioState.js';
import { previewFor } from './studioPreview.js';
import useStudioTape from './useStudioTape.js';
import RailNav from './RailNav.jsx';
import StudioHeader from './StudioHeader.jsx';
import StudioErrorBanner from './StudioErrorBanner.jsx';
import StatusWord from './StatusWord.jsx';
import LiveLine from './LiveLine.jsx';
import TapeBox from './TapeBox.jsx';
import ScriptColumn from './ScriptColumn.jsx';
import StudioDock from './StudioDock.jsx';
import './studio.css';
import './studioLive.css';
import './studioParts.css';

// PAPER.bg -> --tk-bg, TAPE.colors.rule -> --tk-tape-rule, and so on: the
// stylesheets only use these variables.
const toVars = (obj, prefix) => Object.fromEntries(Object.entries(obj).map(([k, v]) => [`${prefix}${k}`, v]));
const TAPE_VARS = toVars(TAPE.colors, '--tk-tape-');
const vars = (palette) => ({ ...toVars(palette, '--tk-'), ...TAPE_VARS });

export default function StudioPage() {
  const [selectedPersona, setSelectedPersona] = useState('default');
  const [selectedMode, setSelectedMode] = useState('vad');
  const [selectedReplyLanguage, setSelectedReplyLanguage] = useState('any');

  const { enqueue, flushPlayback, setPlaybackSampleRate, readPlaybackLevel } = usePlaybackQueue();
  const { turnState, processTurnMessage, resetTurnState } = useTurnState();
  const {
    finalTranscriptEntries, currentPartialTranscript, currentAgentPartial,
    updatePartial, finalizeTurn, appendAgentDelta, finalizeAgentTurn,
    interruptAgentTurn, clearActivePartial, resetTranscript,
  } = useTranscript();
  const {
    isCapturing, micStatus, wsStatus, errorMessage, clearError, startCapture, stopCapture,
    sessionMode, sessionReplyLanguage, pressState, pttStart, pttStop, readMicLevel,
  } = useAudioCapture();
  const { telemetryData, processServerMessage: processTelemetry, resetTelemetry } = useLatencyTelemetry();

  const isTransitioning = wsStatus === 'connecting' || wsStatus === 'connected';
  const isConnected = wsStatus === 'ready';
  // Once session.started has arrived, the server's reply language is shown.
  const shownReplyLanguage = isConnected ? sessionReplyLanguage : selectedReplyLanguage;

  // ── Unchanged from ConversationPage.jsx ──────────────────────────────
  // Central server message router: protocol events to audio, transcript
  // and turn state.
  const handleServerMessage = useCallback((msg) => {
    if (!msg || typeof msg !== 'object') return;
    // Dynamic sample rate for Piper TTS (declared in audio.start)
    if (msg.type === 'audio.start' && msg.sample_rate) {
      setPlaybackSampleRate(msg.sample_rate);
    }
    // User speech transcripts
    if (msg.type === 'transcript.partial') {
      updatePartial(msg.text);
    } else if (msg.type === 'transcript.final') {
      finalizeTurn(msg.text);
    }
    // Backend turn state transitions
    if (msg.type === 'turn.state') {
      processTurnMessage(msg);
      if (msg.state === 'cancelling') {
        interruptAgentTurn('Interrupted', msg.turn_id);
      }
    }
    // Streaming agent replies. The turn_id is kept on the entry, so a later
    // audio.flush for that turn can still mark it interrupted.
    if (msg.type === 'agent.text') {
      processTurnMessage(msg);
      appendAgentDelta(msg.delta, msg.turn_id);
    } else if (msg.type === 'agent.done') {
      processTurnMessage(msg);
      finalizeAgentTurn(msg.text, msg.turn_id);
    }
    // Audio flush command (cancellation). Also marks a reply that was
    // already complete (agent.done) but still playing.
    if (msg.type === 'audio.flush') {
      interruptAgentTurn('Interrupted', msg.turn_id);
    }
    // Server error: the reply text already streamed is KEPT as a transcript
    // line (no agent.done follows TTS_FAILED); only the user's partial is
    // cleared. The banner says what went wrong.
    if (msg.type === 'error') {
      finalizeAgentTurn();
      updatePartial(null);
    }
  }, [setPlaybackSampleRate, updatePartial, finalizeTurn, processTurnMessage, appendAgentDelta, finalizeAgentTurn, interruptAgentTurn]);

  // ── Studio: watch the same messages, after the handler above ─────────
  const startRef = useRef(null);  // performance.now() at session.started
  const cutsRef = useRef([]);     // session seconds of every barge-in (tape)
  const latchedRef = useRef(false);
  const [startWall, setStartWall] = useState(null); // Date.now() at session.started
  const [cutAt, setCutAt] = useState(null);         // seconds of the latched cut

  const onServerMessage = useCallback((msg) => {
    handleServerMessage(msg);
    if (!msg || typeof msg !== 'object') return;
    processTelemetry(msg); // ignores everything but telemetry messages
    if (msg.type === 'session.started') {
      startRef.current = performance.now();
      cutsRef.current = [];
      latchedRef.current = false;
      setStartWall(Date.now());
      setCutAt(null);
      resetTelemetry();
    } else if (isCutMessage(msg)) {
      // One barge-in sends both turn.state cancelling and audio.flush:
      // the latch makes it one cut.
      if (!latchedRef.current && startRef.current !== null) {
        const s = (performance.now() - startRef.current) / 1000;
        latchedRef.current = true;
        cutsRef.current = [...cutsRef.current, s];
        setCutAt(s);
      }
    } else if (msg.type === 'turn.state' && !cutStillLatched(msg.state)) {
      latchedRef.current = false;
      setCutAt(null);
    }
  }, [handleServerMessage, processTelemetry, resetTelemetry]);

  // ── Unchanged from ConversationPage.jsx (but for onServerMessage) ────
  const handleConnect = useCallback(() => {
    if (isCapturing) return;
    resetTranscript();
    resetTurnState();
    startCapture(enqueue, flushPlayback, selectedPersona, onServerMessage, selectedMode, selectedReplyLanguage);
  }, [isCapturing, resetTranscript, resetTurnState, startCapture, enqueue, flushPlayback, selectedPersona, onServerMessage, selectedMode, selectedReplyLanguage]);

  const handleSpeak = useCallback(() => {
    const cutTurnId = pttStart();
    if (cutTurnId) {
      interruptAgentTurn('Interrupted', cutTurnId);
    }
  }, [pttStart, interruptAgentTurn]);

  const handleDisconnect = useCallback(() => {
    clearActivePartial();
    resetTurnState();
    stopCapture();
  }, [clearActivePartial, resetTurnState, stopCapture]);

  useEffect(() => {
    if (wsStatus === 'disconnected' || wsStatus === 'error') {
      clearActivePartial();
      resetTurnState();
    }
  }, [wsStatus, clearActivePartial, resetTurnState]);

  const isMicDenied = micStatus === 'denied';
  const isConnectionDropped = Boolean(errorMessage && errorMessage.toLowerCase().includes('connection'));

  // ── What the page shows ─────────────────────────────────────────────
  const [params] = useSearchParams();
  // DEV only: in a production build this whole expression is `null`.
  const preview = import.meta.env.DEV ? previewFor(params.get('preview')) : null;
  const d = preview
    ? { ...preview, wsStatus: 'ready', isCapturing: true, isConnected: true, cutLatched: preview.cut }
    : {
      wsStatus, turnState, isCapturing, isConnected, cutLatched: cutAt !== null, startWall,
      entries: finalTranscriptEntries, partialUser: currentPartialTranscript, agentPartial: currentAgentPartial,
      readMic: readMicLevel, readPlayback: readPlaybackLevel,
    };
  const fatal = isMicDenied || isConnectionDropped || wsStatus === 'error';
  const view = viewFor({ wsStatus: d.wsStatus, turnState: d.turnState, fatal, cutLatched: d.cutLatched });
  const lamp = VIEWS[view].lamp ?? VIEWS[d.turnState]?.lamp ?? VIEWS.ready.lamp;
  const lampTone = view === 'standby' || view === 'offair' ? 'off' : view === 'tuning' ? 'wait' : 'on';

  // Ink mode: the app's dark theme, same storage as the old sidebar toggle.
  const [ink, setInk] = useState(() => document.documentElement.dataset.theme === 'dark');
  const toggleInk = useCallback(() => {
    const next = ink ? 'light' : 'dark';
    applyTheme(next, document.documentElement);
    saveTheme(next, () => window.localStorage);
    setInk(!ink);
  }, [ink]);

  // The tape: one rAF loop, reading the levels by function, never by state.
  const reducedMotion = useReducedMotion();
  const canvasRef = useRef(null);
  const counterRef = useRef(null);
  const scriptRef = useRef(null);
  useEffect(() => {
    if (preview && startRef.current === null) {
      startRef.current = performance.now(); // DEV preview: a session "now"
      if (preview.cut) cutsRef.current = [1.5];
    }
  });
  useStudioTape({ canvasRef, counterRef, startRef, cutsRef }, {
    live: d.isConnected, thinking: d.turnState === 'thinking', reducedMotion,
    readMic: d.readMic, readPlayback: d.readPlayback,
  });

  const settings = {
    persona: selectedPersona, onPersona: setSelectedPersona,
    language: shownReplyLanguage, onLanguage: setSelectedReplyLanguage,
    mode: selectedMode, onMode: setSelectedMode, locked: d.isCapturing,
  };
  const script = {
    entries: d.entries, partialUser: d.partialUser, agentPartial: d.agentPartial,
    thinking: d.turnState === 'thinking', startWall: d.startWall,
  };

  return (
    <div className="tk" style={vars(ink ? INK : PAPER)}>
      <svg className="tk-grain" aria-hidden="true">
        <filter id="tk-grain-f"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" /></filter>
        <rect width="100%" height="100%" filter="url(#tk-grain-f)" />
      </svg>
      <RailNav ink={ink} onToggleInk={toggleInk} />
      <div className="tk-col">
        <StudioHeader settings={settings} lamp={lamp} lampTone={lampTone} ink={ink} onToggleInk={toggleInk} />
        <StudioErrorBanner errorMessage={errorMessage} isMicDenied={isMicDenied} isConnectionDropped={isConnectionDropped}
          isCapturing={isCapturing} onRetry={handleConnect} onDismiss={clearError} />
        <div className="tk-body">
          <main className="tk-stage">
            <StatusWord view={view} cutTimecode={cutAt !== null ? timecode(cutAt) : preview?.cut ? timecode(1.5) : null} />
            <LiveLine view={view} entries={d.entries} partialUser={d.partialUser} agentPartial={d.agentPartial} />
            <TapeBox view={view} persona={selectedPersona} mode={d.isConnected ? sessionMode : selectedMode}
              language={shownReplyLanguage} canvasRef={canvasRef} />
            <div className="tk-phone-only tk-mini-script">
              <ScriptColumn {...script} limit={3} />
            </div>
          </main>
          <aside className="tk-aside tk-wide-only" aria-label={TEXT.script}>
            <ScriptColumn {...script} title={TEXT.script} footer latencyMs={telemetryData?.totalMs ?? null} />
          </aside>
        </div>
        <StudioDock isCapturing={d.isCapturing} isConnected={d.isConnected} isTransitioning={isTransitioning}
          sessionMode={sessionMode} pressState={pressState} onConnect={handleConnect} onDisconnect={handleDisconnect}
          onSpeak={handleSpeak} onStop={pttStop} onOpenScript={() => scriptRef.current?.showModal()} counterRef={counterRef} />
      </div>
      <dialog ref={scriptRef} className="tk-sheet tk-sheet-script" aria-label={TEXT.scriptDialog}>
        <ScriptColumn {...script} title={TEXT.script} footer latencyMs={telemetryData?.totalMs ?? null} />
        <button type="button" className="tk-mono tk-pill tk-sheet-close" onClick={() => scriptRef.current?.close()}>
          {TEXT.close}
        </button>
      </dialog>
    </div>
  );
}
