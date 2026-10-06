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

import { useState, useCallback } from 'react';

export function useTranscript() {
  // Immutable list of finalized speech turns: Array<{ id: string, role: 'user'|'agent', text: string, timestamp: number, interrupted?: boolean }>
  const [finalTranscriptEntries, setFinalTranscriptEntries] = useState([]);

  // Active partial transcript currently being spoken by the user (string or null)
  const [currentPartialTranscript, setCurrentPartialTranscript] = useState(null);

  // Active partial response from agent currently streaming (string or null)
  const [currentAgentPartial, setCurrentAgentPartial] = useState(null);

  /**
   * Update the currently active partial transcript from the user.
   * Replaces any existing partial text in-place.
   * Does NOT append to finalTranscriptEntries.
   *
   * @param {string|null} text - Recognized partial speech string.
   */
  const updatePartial = useCallback((text) => {
    if (typeof text !== 'string' || !text.trim()) {
      setCurrentPartialTranscript(null);
      return;
    }
    setCurrentPartialTranscript(text);
  }, []);

  /**
   * Finalize the user's speech turn.
   * Converts the active partial (or explicitly provided text) into an immutable
   * permanent transcript entry, and clears the active partial state.
   *
   * @param {string} [text] - Optional finalized text. If omitted, uses current partial.
   */
  const finalizeTurn = useCallback((text) => {
    setCurrentPartialTranscript((currentPartial) => {
      const finalText = text !== undefined ? text : currentPartial;
      if (typeof finalText === 'string' && finalText.trim()) {
        const entry = {
          id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          role: 'user',
          text: finalText.trim(),
          timestamp: Date.now(),
        };
        setFinalTranscriptEntries((prev) => [...prev, entry]);
      }
      return null;
    });
  }, []);

  /**
   * Update or replace streaming text for agent's reply.
   */
  const updateAgentPartial = useCallback((text) => {
    if (typeof text !== 'string' || !text.trim()) {
      setCurrentAgentPartial(null);
      return;
    }
    setCurrentAgentPartial(text);
  }, []);

  /**
   * Append delta to streaming agent reply progressively.
   */
  const appendAgentDelta = useCallback((delta) => {
    if (!delta) return;
    setCurrentAgentPartial((prev) => (prev ? prev + delta : delta));
  }, []);

  /**
   * Finalize the agent's turn normally with complete text.
   */
  const finalizeAgentTurn = useCallback((text) => {
    setCurrentAgentPartial((currentPartial) => {
      const finalText = text !== undefined && text !== null ? text : currentPartial;
      if (typeof finalText === 'string' && finalText.trim()) {
        const entry = {
          id: `agent-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          role: 'agent',
          text: finalText.trim(),
          timestamp: Date.now(),
          interrupted: false,
        };
        setFinalTranscriptEntries((prev) => [...prev, entry]);
      }
      return null;
    });
  }, []);

  /**
   * Mark an in-flight agent turn as interrupted (e.g. on audio.flush or state cancelling).
   * Preserves whatever text was received so far and labels it clearly as interrupted.
   *
   * @param {string} [reason='Interrupted'] - Description of cancellation cause.
   */
  const interruptAgentTurn = useCallback((reason = 'Interrupted') => {
    setCurrentAgentPartial((currentPartial) => {
      if (typeof currentPartial === 'string' && currentPartial.trim()) {
        const entry = {
          id: `agent-interrupted-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          role: 'agent',
          text: currentPartial.trim(),
          timestamp: Date.now(),
          interrupted: true,
          interruptedReason: reason,
        };
        setFinalTranscriptEntries((prev) => [...prev, entry]);
      }
      return null;
    });
  }, []);

  /**
   * Clear active partial transcripts without committing them as final.
   * Used on session disconnect or socket reset.
   */
  const clearActivePartial = useCallback(() => {
    setCurrentPartialTranscript(null);
    setCurrentAgentPartial(null);
  }, []);

  /**
   * Reset all transcript state (both finalized entries and active partials).
   * Used when starting a new session to ensure a clean slate.
   */
  const resetTranscript = useCallback(() => {
    setFinalTranscriptEntries([]);
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
