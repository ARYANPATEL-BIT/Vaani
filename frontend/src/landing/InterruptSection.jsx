/**
 * InterruptSection -- "Interrupting": what happens, in order, when you
 * speak over Vaani. Three frosted cards on a ribbed dark backdrop.
 */

import { INTERRUPT } from './landingContent.js';

export default function InterruptSection() {
  return (
    <section id="interrupt" className="lp-dark lp-interrupt" aria-labelledby="lp-int-title">
      <div className="lp-arc" aria-hidden="true" />
      <div className="lp-inner lp-int-inner">
        <div className="lp-reveal lp-int-head">
          <p className="lp-eyebrow lp-soft">{INTERRUPT.eyebrow}</p>
          <h2 id="lp-int-title" className="lp-h2">
            {INTERRUPT.title[0]}<span className="lp-serif">{INTERRUPT.title[1]}</span>
          </h2>
          <p className="lp-lead lp-soft">{INTERRUPT.intro}</p>
        </div>
        <ol className="lp-int-list">
          {INTERRUPT.steps.map((step) => (
            <li key={step.num} className="lp-reveal lp-glass">
              <div>
                <span className="lp-serif lp-glass-num">{step.num}</span>
                <h3>{step.name}</h3>
              </div>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
        <div className="lp-center">
          <a href={INTERRUPT.link.href} className="lp-cta lp-cta-sm">{INTERRUPT.link.label}</a>
        </div>
      </div>
    </section>
  );
}
