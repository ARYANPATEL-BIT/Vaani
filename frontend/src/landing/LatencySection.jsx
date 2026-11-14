/**
 * LatencySection -- the quality bar: the project's latency TARGET, the
 * measured P50 (a marked placeholder until LATENCY.measuredP50Ms is set in
 * landingContent.js), and the four design principles.
 */

import { Cpu, CircleStop, SlidersHorizontal, ShieldCheck } from 'lucide-react';
import { LATENCY } from './landingContent.js';

const ICONS = { cpu: Cpu, stop: CircleStop, sliders: SlidersHorizontal, shield: ShieldCheck };

function Measured() {
  if (LATENCY.measuredP50Ms === null) {
    // Deliberately looks unfinished (dashed outline): no number is shown
    // until a real run has measured one.
    return <span className="lp-placeholder">Measured P50: not measured yet (placeholder)</span>;
  }
  return (
    <span className="lp-muted-sm">
      Measured P50: {LATENCY.measuredP50Ms} ms{LATENCY.measuredSource && ` (${LATENCY.measuredSource})`}
    </span>
  );
}

export default function LatencySection() {
  return (
    <section id="latency" className="lp-light lp-latency" aria-labelledby="lp-lat-title">
      <div className="lp-inner lp-lat-inner">
        <div className="lp-lat-row">
          <div className="lp-reveal lp-lat-copy">
            <span className="lp-eyebrow">{LATENCY.eyebrow}</span>
            <h2 id="lp-lat-title" className="lp-h2 lp-h2-sm">
              {LATENCY.title[0]}<span className="lp-serif">{LATENCY.title[1]}</span>
            </h2>
            <p className="lp-lead lp-grey">{LATENCY.text}</p>
            <ul className="lp-chips">
              {LATENCY.chips.map((chip) => <li key={chip} className="lp-serif">{chip}</li>)}
            </ul>
          </div>
          <div className="lp-reveal lp-lat-card lp-dark">
            <span className="lp-muted-sm">{LATENCY.targetLabel}</span>
            <p className="lp-lat-number">
              {LATENCY.target}<span className="lp-serif lp-lat-unit">{LATENCY.unit}</span>
            </p>
            <Measured />
          </div>
        </div>
        <div className="lp-principles">
          {LATENCY.principles.map((item, i) => {
            const Icon = ICONS[item.icon];
            return (
              <div key={item.name} className={i === 0 ? 'lp-reveal lp-principle lp-principle-first' : 'lp-reveal lp-principle'}>
                <Icon size={22} strokeWidth={1.6} aria-hidden="true" />
                <h3>{item.name}</h3>
                <p>{item.text}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
