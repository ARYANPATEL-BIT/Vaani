/**
 * useTranscript — React hook managing real-time speech transcript state.
 *
 * Implements the two-state transcript model specified in Week 2, Day 2:
 * 1. Active Partial Transcript: live-updating intermediate recognition results.
 *    Updates in-place as new partial text arrives. Does NOT create an entry
 *    in the permanent transcript list.
 * 2. Finalized Transcript Entries: immutable list of completed speech turns.
 *    Once finalized, an entry remains fixed in place and is never modified
 *    by subsequent partial or final results.
 *
 * Lifecycle guarantees:
 * - When a new session starts: prior transcripts are reset so stale data does
 *   not bleed into the new session.
 * - When the session disconnects: active partial transcript is cleared so
 *   in-flight unfinalized text does not linger.
 */

import { useState, useCallback } from 'react';

export function useTranscript() {
  // Immutable list of finalized speech turns: Array<{ id: string, text: string, timestamp: number }>
  const [finalTranscriptEntries, setFinalTranscriptEntries] = useState([]);

  // Active partial transcript currently being spoken (string or null)
  const [currentPartialTranscript, setCurrentPartialTranscript] = useState(null);

  /**
   * Update the currently active partial transcript.
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
   * Finalize the current speech turn.
   * Converts the active partial (or explicitly provided text) into an immutable
   * permanent transcript entry, and clears the active partial state.
   *
   * @param {string} [text] - Optional finalized text. If omitted, uses the current partial.
   */
  const finalizeTurn = useCallback((text) => {
    setCurrentPartialTranscript((currentPartial) => {
      const finalText = text !== undefined ? text : currentPartial;
      if (typeof finalText === 'string' && finalText.trim()) {
        const entry = {
          id: `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          text: finalText.trim(),
          timestamp: Date.now(),
        };
        setFinalTranscriptEntries((prev) => [...prev, entry]);
      }
      return null;
    });
  }, []);

  /**
   * Clear the active partial transcript without committing it as final.
   * Used on session disconnect, cancel, or socket error.
   */
  const clearActivePartial = useCallback(() => {
    setCurrentPartialTranscript(null);
  }, []);

  /**
   * Reset all transcript state (both finalized entries and active partial).
   * Used when starting a new session to ensure a clean slate.
   */
  const resetTranscript = useCallback(() => {
    setFinalTranscriptEntries([]);
    setCurrentPartialTranscript(null);
  }, []);

  return {
    finalTranscriptEntries,
    currentPartialTranscript,
    updatePartial,
    finalizeTurn,
    clearActivePartial,
    resetTranscript,
  };
}
