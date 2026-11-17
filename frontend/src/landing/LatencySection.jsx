/**
 * LatencySection -- "05 The quality bar": the target "<1,000 ms" whose
 * digits roll into place on scroll, a plain statement that it is not yet
 * measured, and the four principles.
 *
 * Each digit is a column of ten numbers in a box one number tall. The
 * scroll-driven animation (sections.css) slides the column up, so the
 * digits flick past and the real one lands last. The timeline is the whole
 * number line's trip through the screen (--lp-digits), not each column's:
 * a column is ten digits tall, so its own trip would end far too late.
 * Without scroll-driven CSS the column simply sits at its end, showing the
 * real digit.
 */

import { LATENCY } from './landingContent.js';

const { from, to, step } = LATENCY.roll;
const DIGITS = [...LATENCY.target].map((ch, i) => {
  if (!/\d/.test(ch)) return { ch, still: true };
  // Nine decoy digits (a fixed pattern, so the page renders the same each
  // time), then the real one at the bottom of the column.
  const seq = Array.from({ length: 9 }, (_, j) => String((j * 7 + i * 3 + 4) % 10));
  seq.push(ch);
  return { ch, seq, range: `cover ${from + i * step}% cover ${to + i * step}%` };
});

export default function LatencySection() {
  const ms = LATENCY.measuredP50Ms;
  return (
    <section id="latency" className="lp-latency-sec lp-on-ink" aria-labelledby="lp-latency-title">
      <div className="lp-wrap lp-latency">
        <h2 id="lp-latency-title" className="lp-mono lp-eyebrow">{LATENCY.eyebrow}</h2>
        <div className="lp-latency-row">
          <p className="lp-cd lp-latency-num">
            <span className="lp-sr">{LATENCY.targetSpoken}</span>
            <span className="lp-latency-lt" aria-hidden="true">&lt;</span>
            {DIGITS.map((d, i) => (d.still
              ? <span key={i} aria-hidden="true" className="lp-dg-still">{d.ch}</span>
              : (
                <span key={i} aria-hidden="true" className="lp-dg">
                  <span className="lp-dgs" style={{ animationRange: d.range }}>
                    {d.seq.map((q, j) => <span key={j}>{q}</span>)}
                  </span>
                </span>
              )))}
          </p>
          <div className="lp-latency-unit">
            <span className="lp-mono lp-latency-ms">{LATENCY.unit}</span>
            <span className="lp-mono lp-muted lp-latency-cap">{LATENCY.caption}</span>
          </div>
        </div>
        <p className="lp-mono lp-latency-note">
          {ms === null
            ? LATENCY.notMeasured
            : `${LATENCY.measured}: ${ms} ${LATENCY.unit} (${LATENCY.measuredSource})`}
        </p>
        <div className="lp-rules">
          {LATENCY.rules.map((r) => (
            <div key={r.n} className="lp-rule">
              <span className="lp-mono lp-rule-n">{r.n}</span>
              <h3 className="lp-rule-name">{r.name}</h3>
              <p className="lp-muted lp-rule-text">{r.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
