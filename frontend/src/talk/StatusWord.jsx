/**
 * StatusWord -- the giant READY. / LISTENING. / THINKING. / SPEAKING. /
 * CUT. word with its small hint.
 *
 * role="status" makes it a polite live region: when the word changes, a
 * screen reader says the new word after it finishes what it is saying. The
 * hint is not in the region, so only the word is announced.
 */

import { VIEWS } from './talkContent.js';

export default function StatusWord({ view, cutTimecode }) {
  const v = VIEWS[view];
  const hint = v.hint.replace('{cut}', cutTimecode ?? '');
  return (
    <div className="tk-status">
      <p className={view === 'cut' || view === 'offair' ? 'tk-cd tk-word tk-word-red' : 'tk-cd tk-word'} role="status">
        {v.word}<span className="tk-dot" aria-hidden="true">.</span>
      </p>
      <p className="tk-mono tk-hint">{hint}</p>
    </div>
  );
}
