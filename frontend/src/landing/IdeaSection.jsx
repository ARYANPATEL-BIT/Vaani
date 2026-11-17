/**
 * IdeaSection -- "01 The idea": the manifesto, each word lighting up as the
 * section scrolls through the screen.
 *
 * The section declares a named view timeline (--lp-idea, in sections.css):
 * a timeline whose 0% to 100% is the section's journey from entering the
 * screen to leaving it. Every word runs the same fade-in on that timeline,
 * but over its own slice of it (animation-range), and the slices march
 * forward word by word, so the words light up in reading order.
 */

import { IDEA } from './landingContent.js';

const words = IDEA.text.split(' ');
const { start, span, width } = IDEA.range;
const WORDS = words.map((t, i) => {
  const from = start + (i / words.length) * span;
  return {
    t,
    red: IDEA.redWords.includes(t),
    range: `cover ${from.toFixed(1)}% cover ${(from + width).toFixed(1)}%`,
  };
});

export default function IdeaSection() {
  return (
    <section id="idea" className="lp-idea lp-on-ink" aria-labelledby="lp-idea-title">
      <div className="lp-wrap lp-idea-inner">
        <h2 id="lp-idea-title" className="lp-mono lp-eyebrow">{IDEA.eyebrow}</h2>
        <p className="lp-idea-text">
          {WORDS.map((w, i) => (
            <span key={i} className={w.red ? 'lp-word lp-word-red' : 'lp-word'}
              style={{ animationRange: w.range }}>
              {w.t}{' '}
            </span>
          ))}
        </p>
      </div>
    </section>
  );
}
