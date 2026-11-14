/**
 * DemoCard -- the frosted card under the wave that plays the scripted
 * conversation. It is not live: there is no microphone and no connection,
 * and it says so ("Scripted demo"). The text comes from demoScript.js.
 */

import { ACCENT, CUT_COLOUR, THINK_COLOUR, DEMO } from './landingContent.js';

const DOT = { speak: ACCENT, cut: CUT_COLOUR, listen: ACCENT, think: THINK_COLOUR, idle: ACCENT };

export default function DemoCard({ demo }) {
  return (
    // aria-live off: the text changes several times a second while it
    // "types"; announcing each change would drown out a screen reader.
    <div className="lp-demo" aria-live="off">
      <div className="lp-demo-head">
        <span className="lp-demo-dot" style={{ background: DOT[demo.phase] }} />
        <span>{DEMO.labels[demo.phase]}</span>
        <span className="lp-demo-badge">{DEMO.badge}</span>
      </div>
      <p><strong>Vaani:</strong> {demo.vaani}</p>
      {demo.user && <p><strong>You:</strong> {demo.user}</p>}
      {demo.reply && <p><strong>Vaani:</strong> {demo.reply}</p>}
    </div>
  );
}
