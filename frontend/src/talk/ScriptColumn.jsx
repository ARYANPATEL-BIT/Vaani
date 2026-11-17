/**
 * ScriptColumn -- the numbered record of the conversation.
 *
 * Finished turns are a real ordered list (<ol>) inside role="log", a polite
 * live region meant for chat-like logs: a screen reader announces each new
 * turn as it is added. The turn still being spoken or written is shown
 * below the list, outside the live region, so its changing words are not
 * read out on every update.
 *
 * Used three ways: the desktop column (full, with the latency footer), the
 * phone's last few turns (limit), and the phone's full-script sheet.
 */

import { memo, useEffect, useRef } from 'react';
import { TEXT } from './talkContent.js';
import { timecode } from './studioState.js';

const num = (n) => String(n).padStart(2, '0');

function Turn({ n, who, time, children, live, cut }) {
  return (
    <li className={live ? 'tk-turn tk-turn-live' : 'tk-turn'}>
      <span className="tk-cd tk-turn-n" aria-hidden="true">{num(n)}</span>
      <span className={`tk-mono tk-turn-tag${who === 'you' ? ' tk-turn-you' : ''}`}>
        {who === 'you' ? TEXT.you : TEXT.vaani}
        {time && <span className="tk-turn-time">{time}</span>}
      </span>
      <p className="tk-turn-text">
        {children}
        {cut && <span className="tk-mono tk-tag-cut">{TEXT.cutTag}</span>}
        {live && <span className="tk-live-dot" aria-hidden="true" />}
      </p>
    </li>
  );
}

function ScriptColumn({ entries, partialUser, agentPartial, thinking, startWall, limit, latencyMs, footer, title }) {
  const scrollRef = useRef(null);
  const first = limit ? Math.max(0, entries.length - limit) : 0;
  const shown = entries.slice(first);
  const at = (ts) => (startWall ? timecode((ts - startWall) / 1000) : null);
  // Numbers for the live turns, after the finished ones.
  const youN = entries.length + 1;
  const vaaniN = partialUser ? youN + 1 : youN;

  // Keep the newest turn in view. Instant, not smooth: no motion to opt out of.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length, partialUser, agentPartial]);

  return (
    <div className="tk-script">
      {title && (
        <div className="tk-script-head">
          <h2 className="tk-cd tk-script-title">{title}</h2>
          <span className="tk-mono tk-chip">{TEXT.turns(entries.length)}</span>
        </div>
      )}
      <div className="tk-script-list" ref={scrollRef}>
        <div role="log" aria-live="polite" aria-label={TEXT.script}>
          <ol className="tk-turns" start={first + 1}>
            {shown.map((e, i) => (
              <Turn key={e.id} n={first + i + 1} who={e.role === 'user' ? 'you' : 'vaani'}
                time={at(e.timestamp)} cut={e.interrupted}>
                {e.text}
              </Turn>
            ))}
          </ol>
        </div>
        {(partialUser || agentPartial || thinking) && (
          <ol className="tk-turns" start={youN} aria-label={TEXT.liveTag}>
            {partialUser && <Turn n={youN} who="you" live>{partialUser}</Turn>}
            {(agentPartial || thinking) && <Turn n={vaaniN} who="vaani" live>{agentPartial || '…'}</Turn>}
          </ol>
        )}
      </div>
      {footer && (
        <div className="tk-latency">
          <div>
            <span className="tk-mono tk-small">{TEXT.latencyLabel}</span>
            <span className="tk-cd tk-latency-num">
              {latencyMs == null ? TEXT.latencyEmpty : Math.round(latencyMs)}
              <span className="tk-mono tk-latency-unit">{TEXT.latencyUnit}</span>
            </span>
          </div>
          <span className="tk-mono tk-small tk-latency-note">
            {TEXT.latencyTarget}<br />{latencyMs == null ? TEXT.latencyNone : TEXT.latencyHas}
          </span>
        </div>
      )}
    </div>
  );
}

// memo: skip re-rendering on the page's per-frame re-renders (see LiveLine).
export default memo(ScriptColumn);
