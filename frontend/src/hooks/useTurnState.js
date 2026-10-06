/**
 * useTurnState — React hook mirroring the backend turn state machine.
 *
 * Wire protocol source:
 * - backend/vaani/turn_state.py (states: idle, listening, thinking, speaking, cancelling)
 * - backend/vaani/protocol.py (TurnStateMessage, AgentText, AgentDone)
 * - docs/contracts.md §2.5
 *
 * State flow:
 *   idle → listening → thinking → speaking → idle
 *   cancelling is a transient state when a turn is cancelled or flushed.
 *
 * Real agent response accumulation:
 *   agent.text  → delta streaming fragments accumulated in agentDraft
 *   agent.done  → finalized complete reply text
 */

import { useState, useCallback } from 'react';
import {
  TURN_STATES,
  VALID_TURN_STATES,
  validateTurnState,
  validateAgentText,
  validateAgentDone,
} from '../turnState/turnContracts.js';

export { TURN_STATES, VALID_TURN_STATES };

export function useTurnState() {
  const [turnState, setTurnState] = useState(TURN_STATES.IDLE);
  const [turnId, setTurnId] = useState(null);
  const [agentDraft, setAgentDraft] = useState(null);
  const [lastAgentMessage, setLastAgentMessage] = useState(null);

  /**
   * Process incoming WebSocket JSON message for turn state & agent replies.
   * Can be safely called for all JSON messages.
   */
  const processTurnMessage = useCallback((msg) => {
    if (!msg || typeof msg !== 'object') return;

    if (msg.type === 'turn.state') {
      const parsed = validateTurnState(msg);
      if (parsed.valid) {
        setTurnState(parsed.state);
        setTurnId(parsed.turnId);
        if (parsed.state === TURN_STATES.IDLE || parsed.state === TURN_STATES.CANCELLING) {
          setAgentDraft(null);
        }
      }
      return;
    }

    if (msg.type === 'agent.text') {
      const parsed = validateAgentText(msg);
      if (parsed.valid) {
        setAgentDraft((prev) => (prev ? prev + parsed.delta : parsed.delta));
      }
      return;
    }

    if (msg.type === 'agent.done') {
      const parsed = validateAgentDone(msg);
      if (parsed.valid) {
        setLastAgentMessage(parsed.text);
        setAgentDraft(null);
      }
      return;
    }
  }, []);

  const resetTurnState = useCallback(() => {
    setTurnState(TURN_STATES.IDLE);
    setTurnId(null);
    setAgentDraft(null);
    setLastAgentMessage(null);
  }, []);

  return {
    turnState,
    turnId,
    agentDraft,
    lastAgentMessage,
    processTurnMessage,
    resetTurnState,
  };
}
