/**
 * LiveLine -- the big words under the status: what is being said now.
 *
 * Colour says WHO: the user's words are red, Vaani's are ink.
 * Fill says HOW SURE: outlined words are not final, solid words are.
 *   - The user's interim transcript (transcript.partial) is outlined; the
 *     final one is solid.
 *   - Vaani's reply text is outlined only while no audio of the turn has
 *     been played (state thinking). From speaking on, the whole line is
 *     solid: the app cannot tell which words have been heard, because the
 *     audio carries no word timings, so it does not pretend to.
 * On a cut, Vaani's interrupted line is drawn twice, each copy clipped to
 * one half and nudged apart, with a red line between: a slice.
 *
 * aria-hidden: the same words are in the Script list, which is the
 * accessible record. Reading them twice would only add noise.
 */

import { memo } from 'react';
import { LIVE, TEXT } from './talkContent.js';
import { tail } from './studioState.js';

const lastOf = (entries, role) => {
  for (let i = entries.length - 1; i >= 0; i--) if (entries[i].role === role) return entries[i];
  return null;
};

function lines({ view, entries, partialUser, agentPartial }) {
  const user = lastOf(entries, 'user');
  const agent = lastOf(entries, 'agent');
  const userLine = partialUser
    ? { who: 'you', text: partialUser, outlined: true }
    : null;
  switch (view) {
    case 'listening':
      return { rows: userLine ? [userLine] : [] };
    case 'thinking':
      return {
        rows: [
          user && { who: 'you', text: user.text, outlined: false },
          agentPartial && { who: 'vaani', text: agentPartial, outlined: true },
        ].filter(Boolean),
      };
    case 'speaking': {
      const text = agentPartial ?? agent?.text;
      return { rows: text ? [{ who: 'vaani', text, outlined: false }] : [] };
    }
    case 'cut': {
      // The user's words after the cut: the interim line, or the final one
      // if it has already landed after the cut reply.
      const after = userLine
        ?? (user && agent && user.timestamp > agent.timestamp ? { who: 'you', text: user.text, outlined: false } : null);
      return { slice: agent?.interrupted ? agent.text : null, rows: after ? [after] : [] };
    }
    default:
      return { rows: [] };
  }
}

function LiveLine(props) {
  const { slice, rows } = lines(props);
  const empty = !slice && rows.length === 0;
  return (
    <div className="tk-live" aria-hidden="true">
      {empty && (
        <p className="tk-cd tk-line tk-line-sm">
          <span className="tk-ol">{TEXT.placeholder}</span>
          <span className="tk-cursor" />
        </p>
      )}
      {slice && (
        <div className="tk-slice">
          <p className="tk-cd tk-line tk-slice-top"><span>{tail(slice, LIVE.maxChars / 2)}</span></p>
          <p className="tk-cd tk-line tk-slice-bottom"><span>{tail(slice, LIVE.maxChars / 2)}</span></p>
          <span className="tk-slice-rule" />
        </div>
      )}
      {rows.map((r) => (
        <p key={r.who} className={`tk-cd tk-line${r.who === 'you' ? ' tk-line-you' : ''}${slice ? ' tk-line-sm' : ''}`}>
          <span className={r.outlined ? 'tk-ol' : undefined}>{tail(r.text, LIVE.maxChars)}</span>
        </p>
      ))}
    </div>
  );
}

// memo: the page re-renders on every mic frame it sends (useAudioCapture's
// framesSent counter). memo skips this component unless its props changed.
export default memo(LiveLine);
