/**
 * PipelineSection -- "How it works": the five steps from your voice to the
 * reply. One big panel shows the current step; five buttons pick a step.
 *
 * Auto-advance has no JavaScript timer. The active button's progress line
 * is a CSS animation (lp-fill, advanceS long); when it ends, onAnimationEnd
 * moves to the next step. Pausing is then pure CSS: animation-play-state:
 * paused while the steps are hovered or focused, or while the visitor has
 * pressed "Pause animation" (landing.css / sections.css). It stops for good
 * once the visitor picks a step, and never runs under reduced motion.
 */

import { useState } from 'react';
import { PIPELINE } from './landingContent.js';

const two = (n) => String(n).padStart(2, '0');

export default function PipelineSection({ reducedMotion }) {
  const [step, setStep] = useState(0);
  const [auto, setAuto] = useState(true);
  const advancing = auto && !reducedMotion;
  const total = PIPELINE.steps.length;
  const current = PIPELINE.steps[step];

  function pick(i) {
    setStep(i);
    setAuto(false); // the visitor chose; stop moving under them
  }

  return (
    <section id="pipeline" className="lp-light" aria-labelledby="lp-pipe-title">
      <div className="lp-inner lp-stack-40">
        <div className="lp-eyebrow-row">
          <span className="lp-eyebrow">{PIPELINE.eyebrow}</span>
          <span className="lp-rule" />
        </div>
        <h2 id="lp-pipe-title" className="lp-h2 lp-reveal">
          {PIPELINE.title[0]}<span className="lp-serif">{PIPELINE.title[1]}</span>
        </h2>
        <div className="lp-pipe">
          <div className="lp-pipe-panel lp-dark lp-reveal">
            <div className="lp-pipe-top">
              <span className="lp-serif lp-pipe-num">{two(step + 1)}</span>
              <span className="lp-muted-sm">{step + 1} / {total}</span>
            </div>
            <div className="lp-pipe-text">
              <span className="lp-pipe-kind">{current.kind}</span>
              <h3>{current.name}</h3>
              <p>{current.text}</p>
            </div>
          </div>
          <div className="lp-pipe-steps">
            {PIPELINE.steps.map((s, i) => (
              <button
                key={s.kind}
                type="button"
                className="lp-pipe-step"
                aria-pressed={i === step}
                onClick={() => pick(i)}
              >
                <span className="lp-track">
                  {i === step && (
                    <span
                      className={advancing ? 'lp-fill lp-fill-run' : 'lp-fill'}
                      style={advancing ? { animationDuration: `${PIPELINE.advanceS}s` } : undefined}
                      onAnimationEnd={advancing ? () => setStep((i + 1) % total) : undefined}
                    />
                  )}
                </span>
                <span className="lp-pipe-step-name">{two(i + 1)} {s.kind}</span>
                <span className="lp-pipe-step-short">{s.short}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
