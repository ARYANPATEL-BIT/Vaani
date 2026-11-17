/**
 * StorySection -- "02 When you cut in": three steps beside a sticky dark
 * monitor. The step nearest the middle of the screen is active
 * (useActiveStep.js); the monitor lights the matching lane and shows its
 * note. The reel next to the heading spins only while step 01 is active:
 * playback is running until it is flushed in step 02.
 */

import { IMAGES, STORY } from './landingContent.js';
import useActiveStep from './useActiveStep.js';

const pad = (n) => String(n).padStart(2, '0');

// A lane block at [left %, width %] -> inline position.
const box = ([left, width]) => ({ left: `${left}%`, width: `${width}%` });

export default function StorySection() {
  const [active, refFor] = useActiveStep(STORY.observerMargin);
  const step = STORY.steps[active];

  return (
    <section id="cut" className="lp-story-sec" aria-labelledby="lp-story-title">
      <div className="lp-wrap lp-story-wrap">
        <div className="lp-story-head">
          <div className="lp-story-title-row">
            <img src={IMAGES.reel} alt="" aria-hidden="true" loading="lazy" decoding="async"
              className={active === 0 ? 'lp-reel lp-reel-on' : 'lp-reel'} />
            <h2 id="lp-story-title" className="lp-cd lp-h2">{STORY.title}</h2>
          </div>
          <p className="lp-mono lp-eyebrow">{STORY.eyebrow}</p>
        </div>

        <div className="lp-story">
          {/* The monitor repeats the active step as a picture; the steps
              themselves carry the words, so it is hidden from screen readers. */}
          <div className="lp-monitor lp-on-ink" aria-hidden="true">
            <div className="lp-mono lp-monitor-top">
              <span>{STORY.monitor}</span>
              <span className="lp-monitor-tag">{pad(active + 1)} &middot; {step.tag}</span>
            </div>
            <div className="lp-lanes">
              {STORY.lanes.map((ln) => {
                const on = ln.step === active;
                return (
                  <div key={ln.name} className={on ? 'lp-lane lp-lane-on' : 'lp-lane'}>
                    <span className="lp-mono lp-lane-name">{ln.name}</span>
                    <span className="lp-lane-track">
                      <span className={ln.step === 0 ? 'lp-lane-a lp-lane-a-mic' : 'lp-lane-a'} style={box(ln.a)} />
                      {ln.b && <span className="lp-lane-b" style={box(ln.b)} />}
                      {on && <span className="lp-mono lp-lane-tag">{ln.tag}</span>}
                    </span>
                  </div>
                );
              })}
              <span className="lp-lanes-cut" />
            </div>
            <p className="lp-monitor-note">{step.note}</p>
          </div>

          <ol className="lp-steps">
            {STORY.steps.map((s, i) => (
              <li key={s.name} ref={refFor(i)} className={i === active ? 'lp-step lp-step-on' : 'lp-step'}>
                <span className="lp-cd lp-step-num" aria-hidden="true">{pad(i + 1)}</span>
                <h3 className="lp-step-name">{s.name}</h3>
                <p className="lp-step-text">{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
