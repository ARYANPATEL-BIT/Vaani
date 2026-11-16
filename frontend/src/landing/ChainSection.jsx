/**
 * ChainSection -- "04 Signal chain": the five pipeline steps as dotted
 * credit cells, with a red dot running along the line above them.
 */

import { CHAIN } from './landingContent.js';

const pad = (n) => String(n).padStart(2, '0');

export default function ChainSection() {
  return (
    <section id="chain" className="lp-chain-sec" aria-labelledby="lp-chain-title">
      <div className="lp-wrap lp-chain">
        <div className="lp-chain-head">
          <h2 id="lp-chain-title" className="lp-cd lp-h2">{CHAIN.title}</h2>
          <p className="lp-muted lp-chain-intro">{CHAIN.text}</p>
        </div>
        <div className="lp-chain-line" aria-hidden="true"><span className="lp-run" /></div>
        <ol className="lp-cells">
          {CHAIN.steps.map((c, i) => (
            <li key={c.name} className="lp-cell">
              <span className="lp-mono lp-muted lp-cell-kind">{pad(i + 1)} &mdash; {c.kind}</span>
              <span className="lp-cd lp-cell-name">{c.name}</span>
              <span className="lp-muted lp-cell-text">{c.text}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
