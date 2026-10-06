/**
 * LatencyHud — Heads-Up Display for real-time per-stage latency telemetry.
 *
 * Implements the official Week 3, Day 1 frontend requirement:
 * "Latency HUD reading the telemetry payload, one figure per stage."
 *
 * Contract & stages source:
 * - backend/vaani/telemetry.py (canonical span constants)
 * - docs/findings/perf-1-latency-budget.md (pipeline stages)
 * - docs/contracts.md §2.6 (SHARED PROTOCOL v0.5 telemetry)
 *
 * UI States:
 * 1. No conversation active (wsStatus === 'disconnected')
 * 2. Connected, awaiting telemetry (wsStatus === 'ready', no telemetry yet)
 * 3. Live full telemetry received (all stages populated)
 * 4. Partial telemetry received (some stages populated, missing stages show '—')
 * 5. Session ended (preserves last measured turn with idle status)
 * 6. Connection error / dropped (displays error badge)
 */

import { STAGE_DEFINITIONS, formatLatencyMs } from '../telemetry/latencyTelemetry.js';
import './LatencyHud.css';

export function LatencyHud({
  telemetryData = null,
  wsStatus = 'disconnected',
  isCapturing = false,
}) {
  const hasTelemetry = Boolean(telemetryData && telemetryData.hasData);
  const stages = telemetryData?.stages || {};
  const isPartial = Boolean(telemetryData?.isPartial);
  const turnId = telemetryData?.turnId || null;
  const totalMs = telemetryData?.totalMs ?? null;

  // Determine HUD status badge
  const getStatusBadge = () => {
    if (wsStatus === 'error') {
      return { label: 'Connection dropped', className: 'badge-error', pulse: false };
    }
    if (!isCapturing && wsStatus === 'disconnected') {
      if (hasTelemetry) {
        return { label: 'Session ended (last turn)', className: 'badge-idle', pulse: false };
      }
      return { label: 'No conversation active', className: 'badge-idle', pulse: false };
    }
    if (isCapturing && !hasTelemetry) {
      return { label: 'Waiting for telemetry…', className: 'badge-waiting', pulse: true };
    }
    if (hasTelemetry) {
      if (isPartial) {
        return { label: 'Partial telemetry', className: 'badge-partial', pulse: false };
      }
      return { label: 'Live telemetry', className: 'badge-live', pulse: true };
    }
    return { label: 'Idle', className: 'badge-idle', pulse: false };
  };

  const status = getStatusBadge();

  return (
    <section className="latency-hud-section" id="latency-hud" aria-label="Per-stage latency diagnostics">
      <div className="latency-hud-header">
        <div className="latency-hud-title-wrap">
          <h2 className="latency-hud-title">Latency HUD</h2>
          {turnId && (
            <span className="hud-turn-badge" title={`Turn ID: ${turnId}`}>
              Turn: {turnId.length > 12 ? `${turnId.slice(0, 10)}…` : turnId}
            </span>
          )}
        </div>

        <div className="latency-hud-badges">
          <span className={`latency-status-badge ${status.className}`}>
            {status.pulse && <span className="hud-pulse-dot" />}
            {status.label}
          </span>
        </div>
      </div>

      {/* Empty State Banner (Shown when no telemetry data has arrived yet) */}
      {!hasTelemetry && (
        <div className="latency-hud-empty" id="latency-hud-empty">
          <p className="latency-hud-empty-text">
            {isCapturing
              ? 'Telemetry spans will populate live as speech turns complete.'
              : 'No telemetry available. Connect and begin speaking to measure pipeline latency.'}
          </p>
        </div>
      )}

      {/* Grid of per-stage timings */}
      <div className="latency-stages-grid" role="region" aria-live="polite">
        {STAGE_DEFINITIONS.map((stage) => {
          const val = stages[stage.key];
          const hasVal = typeof val === 'number' && !Number.isNaN(val);
          return (
            <div
              key={stage.key}
              className={`latency-stage-card ${hasVal ? 'stage-active' : 'stage-missing'}`}
              data-testid={`latency-stage-${stage.key}`}
              title={stage.description}
            >
              <div className="stage-card-top">
                <span className="stage-card-label">{stage.label}</span>
                <span className="stage-card-tag">{stage.shortLabel}</span>
              </div>
              <div className={`stage-card-value ${hasVal ? '' : 'value-empty'}`}>
                {formatLatencyMs(val)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Total latency summary */}
      <div className="latency-total-bar">
        <div className="total-bar-left">
          <span className="total-label">Total Pipeline Latency:</span>
          <span className={`total-value ${totalMs !== null ? '' : 'total-empty'}`}>
            {formatLatencyMs(totalMs)}
          </span>
        </div>
        <span className="total-target-note">Target: P50 &lt; 1,000 ms</span>
      </div>
    </section>
  );
}

export default LatencyHud;
