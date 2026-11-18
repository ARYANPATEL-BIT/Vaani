/**
 * StudioDoor -- the black box on the left of /login: a studio door with an
 * ON AIR lamp above it and the operator's mic line below.
 *
 * The lamp has four looks, one per page view:
 *   off / error  grey outline, unlit
 *   checking     red outline, blinking (CSS, none under reduced motion)
 *   refused      sliced through, like a cut reply on /talk: the word twice,
 *                one copy clipped to the part above a slanted line and one
 *                to the part below it, the lower copy nudged away, and a
 *                red rule along the cut
 *   onair        lit red with a glow; the mic bars hum
 * All of it is decoration: the lamp has one role="img" label, the rest is
 * aria-hidden, and the page's words say the same thing in text.
 */

import { BAR_COUNT, LIT_BARS, TEXT, VIEWS } from './loginContent.js';

const SCREWS = ['tl', 'tr', 'bl', 'br'];

function Lamp({ view }) {
  const lit = view === 'onair';
  return (
    <div role="img" aria-label={lit ? TEXT.lampOn : TEXT.lampOff} className={`lg-lamp lg-lamp-${view}`}>
      {view === 'refused' ? (
        <span className="lg-lamp-cut" aria-hidden="true">
          <span className="lg-cd lg-lamp-word lg-cut-top">On air</span>
          <span className="lg-cd lg-lamp-word lg-cut-bottom">On air</span>
          <span className="lg-cut-rule" />
        </span>
      ) : (
        <span className="lg-cd lg-lamp-word" aria-hidden="true">On air</span>
      )}
      {SCREWS.map((s) => <span key={s} className={`lg-screw lg-screw-${s}`} aria-hidden="true" />)}
    </div>
  );
}

// doorStatus: an alert's own door wording (ALERTS.googleDown), else the view's.
export default function StudioDoor({ view, doorStatus }) {
  const v = VIEWS[view];
  const lit = view === 'onair';
  return (
    <section className={`lg-door lg-door-${view}`} aria-label={TEXT.doorLabel}>
      <div className="lg-mono lg-door-bar">
        <span className="lg-door-status">
          <span className="lg-door-dot" aria-hidden="true" />
          {TEXT.doorLabel} · {doorStatus ?? v.door}
        </span>
        {/* Dropped on a phone, where "no line to Google" needs the room. */}
        <span className="lg-wide-only">{TEXT.room}</span>
      </div>
      <div className="lg-door-stage">
        <Lamp view={view} />
      </div>
      <div className="lg-mic">
        <div className="lg-mono lg-mic-label">
          <span>{v.mic}</span>
          <span>{TEXT.timecode}</span>
        </div>
        <div className="lg-bars" aria-hidden="true">
          {/* A lit bar gets its height and a staggered start, so the hum
              ripples instead of every bar moving together. */}
          {Array.from({ length: BAR_COUNT }, (_, i) => (
            <span key={i} className="lg-bar"
              style={lit ? { height: `${LIT_BARS[i]}px`, animationDelay: `${(i % 7) * -0.1}s` } : undefined} />
          ))}
        </div>
      </div>
    </section>
  );
}
