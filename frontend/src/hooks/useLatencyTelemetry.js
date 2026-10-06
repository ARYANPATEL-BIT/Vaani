/**
 * useLatencyTelemetry — React hook managing live per-stage latency telemetry state.
 *
 * Coordinates:
 * 1. Listening for server telemetry messages over the WebSocket session.
 * 2. Parsing and validating the contract-defined telemetry payload.
 * 3. Maintaining live stage timings without freezing or fabricating values.
 * 4. Associating measurements with the current conversation turn.
 * 5. Safely updating the state live as new telemetry frames arrive.
 * 6. Clean lifecycle resets on new session start.
 */

import { useState, useCallback } from 'react';
import { parseTelemetryPayload } from '../telemetry/latencyTelemetry.js';

export function useLatencyTelemetry() {
  // Current active telemetry record:
  // {
  //   valid: boolean,
  //   turnId: string | null,
  //   timestamp: number,
  //   stages: { vad: number|null, endpointing: number|null, asr: number|null, llm: number|null, tts: number|null, playback: number|null },
  //   totalMs: number | null,
  //   hasData: boolean,
  //   isPartial: boolean
  // } | null
  const [telemetryData, setTelemetryData] = useState(null);

  // Monotonically increasing counter of telemetry messages processed
  const [updateCount, setUpdateCount] = useState(0);

  /**
   * Process an incoming server control message.
   * If the message is a telemetry message, parses it and updates state.
   * Ignores non-telemetry messages cleanly.
   *
   * @param {object} serverMessage - Parsed JSON message from WebSocket.
   * @returns {boolean} True if message was a valid telemetry message.
   */
  const processServerMessage = useCallback((serverMessage) => {
    if (!serverMessage || typeof serverMessage !== 'object') {
      return false;
    }

    const { type } = serverMessage;
    if (type !== 'telemetry' && type !== 'telemetry.spans' && type !== 'telemetry.turn') {
      return false;
    }

    const parsed = parseTelemetryPayload(serverMessage);
    if (parsed.valid && parsed.hasData) {
      setTelemetryData(parsed);
      setUpdateCount((c) => c + 1);
      return true;
    }

    return false;
  }, []);

  /**
   * Reset all telemetry state.
   * Invoked when starting a new session to prevent stale data from lingering.
   */
  const resetTelemetry = useCallback(() => {
    setTelemetryData(null);
    setUpdateCount(0);
  }, []);

  return {
    telemetryData,
    hasTelemetry: Boolean(telemetryData && telemetryData.hasData),
    updateCount,
    processServerMessage,
    resetTelemetry,
  };
}
