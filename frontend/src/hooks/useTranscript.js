/**
 * useTranscript — React hook managing real-time speech transcript state.
 *
 * Implements the transcript and agent reply model:
 * 1. Active Partial Transcript: live-updating intermediate recognition results
 *    from the user. Replaces in-place.
 * 2. Active Streaming Agent Reply: live progressive text streamed from agent.text deltas.
 * 3. Finalized Transcript Entries: immutable list of completed turns, with explicit
 *    interruption tracking (`interrupted: boolean`).
 * 4. Interrupted Turns: preserves partial text accumulated prior to cancellation/flush,
 *    clearly marking the turn as interrupted rather than discarding it or pretending
 *    it completed normally.
 *
 * Lifecycle guarantees:
 * - When a new session starts: prior transcripts are reset so stale data does
 *   not bleed into the new session.
 * - When the session disconnects: active partial transcript is cleared so
 *   in-flight unfinalized text does not linger.
 */

import { useState, useRef, useCallback } from 'react';

/**
 * Build one immutable transcript entry. Kept outside the hook so every commit
 * path creates entries the same way.
 */
function makeEntry(role, text, extra = {}) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    role,
    text: text.trim(),
    timestamp: Date.now(),
    ...extra,
  };
}

export function useTranscript() {
  // Immutable list of finalized speech turns: Array<{ id: string, role: 'user'|'agent', text: string, timestamp: number, interrupted?: boolean }>
  const [finalTranscriptEntries, setFinalTranscriptEntries] = useState([]);

  // Active partial transcript currently being spoken by the user (string or null)
  const [currentPartialTranscript, setCurrentPartialTranscript] = useState(null);

  // Active partial response from agent currently streaming (string or null)
  const [currentAgentPartial, setCurrentAgentPartial] = useState(null);

  // Mirrors of the two in-flight texts. The commit functions below read these
  // instead of reading state inside a setState updater. React's StrictMode
  // (main.jsx) runs updater functions twice in development; an updater that
  // itself appends an entry therefore appended every line twice. Refs are read
  // once, synchronously, so each commit happens exactly once.
  const userPartialRef = useRef(null);
  const agentPartialRef = useRef(null);

  /**
   * Update the currently active partial transcript from the user.
   * Replaces any existing partial text in-place.
   * Does NOT append to finalTranscriptEntries.
   *
   * @param {string|null} text - Recognized partial speech string.
   */
  const updatePartial = useCallback((text) => {
    const next = typeof text === 'string' && text.trim() ? text : null;
    userPartialRef.current = next;
    setCurrentPartialTranscript(next);
  }, []);

  /**
   * Finalize the user's speech turn.
   * Converts the active partial (or explicitly provided text) into an immutable
   * permanent transcript entry, and clears the active partial state.
   *
   * @param {string} [text] - Optional finalized text. If omitted, uses current partial.
   */
  const finalizeTurn = useCallback((text) => {
    const finalText = text !== undefined ? text : userPartialRef.current;
    userPartialRef.current = null;
    setCurrentPartialTranscript(null);
    if (typeof finalText === 'string' && finalText.trim()) {
      setFinalTranscriptEntries((prev) => [...prev, makeEntry('user', finalText)]);
    }
  }, []);

  /**
   * Update or replace streaming text for agent's reply.
   */
  const updateAgentPartial = useCallback((text) => {
    const next = typeof text === 'string' && text.trim() ? text : null;
    agentPartialRef.current = next;
    setCurrentAgentPartial(next);
  }, []);

  /**
   * Append delta to streaming agent reply progressively.
   */
  const appendAgentDelta = useCallback((delta) => {
    if (!delta) return;
    agentPartialRef.current = (agentPartialRef.current ?? '') + delta;
    setCurrentAgentPartial(agentPartialRef.current);
  }, []);

  /**
   * Finalize the agent's turn normally with complete text.
   */
  const finalizeAgentTurn = useCallback((text) => {
    const finalText = text !== undefined && text !== null ? text : agentPartialRef.current;
    agentPartialRef.current = null;
    setCurrentAgentPartial(null);
    if (typeof finalText === 'string' && finalText.trim()) {
      setFinalTranscriptEntries((prev) => [
        ...prev,
        makeEntry('agent', finalText, { interrupted: false }),
      ]);
    }
  }, []);

  /**
   * Mark an in-flight agent turn as interrupted (e.g. on audio.flush or state cancelling).
   * Preserves whatever text was received so far and labels it clearly as interrupted.
   *
   * @param {string} [reason='Interrupted'] - Description of cancellation cause.
   */
  const interruptAgentTurn = useCallback((reason = 'Interrupted') => {
    const partial = agentPartialRef.current;
    agentPartialRef.current = null;
    setCurrentAgentPartial(null);
    if (typeof partial === 'string' && partial.trim()) {
      setFinalTranscriptEntries((prev) => [
        ...prev,
        makeEntry('agent', partial, { interrupted: true, interruptedReason: reason }),
      ]);
    }
  }, []);

  /**
   * Clear active partial transcripts without committing them as final.
   * Used on session disconnect or socket reset.
   */
  const clearActivePartial = useCallback(() => {
    userPartialRef.current = null;
    agentPartialRef.current = null;
    setCurrentPartialTranscript(null);
    setCurrentAgentPartial(null);
  }, []);

  /**
   * Reset all transcript state (both finalized entries and active partials).
   * Used when starting a new session to ensure a clean slate.
   */
  const resetTranscript = useCallback(() => {
    setFinalTranscriptEntries([]);
    userPartialRef.current = null;
    agentPartialRef.current = null;
    setCurrentPartialTranscript(null);
    setCurrentAgentPartial(null);
  }, []);

  return {
    finalTranscriptEntries,
    currentPartialTranscript,
    currentAgentPartial,
    updatePartial,
    finalizeTurn,
    updateAgentPartial,
    appendAgentDelta,
    finalizeAgentTurn,
    interruptAgentTurn,
    clearActivePartial,
    resetTranscript,
  };
}
