/**
 * ClosingSection -- the last call to action, over a glowing horizon arc.
 */

import { Link } from 'react-router-dom';
import { Mic } from 'lucide-react';
import { APP_PATH, CLOSING } from './landingContent.js';

export default function ClosingSection() {
  return (
    <section className="lp-dark lp-closing" aria-labelledby="lp-close-title">
      <div className="lp-horizon" aria-hidden="true" />
      <div className="lp-inner lp-reveal lp-closing-inner">
        <h2 id="lp-close-title" className="lp-h2">
          {CLOSING.title[0]}<span className="lp-serif">{CLOSING.title[1]}</span>{CLOSING.title[2]}
        </h2>
        <p className="lp-lead lp-soft">{CLOSING.text}</p>
        <Link to={APP_PATH} className="lp-cta">
          <Mic size={16} strokeWidth={2} aria-hidden="true" />
          {CLOSING.cta}
        </Link>
      </div>
    </section>
  );
}
