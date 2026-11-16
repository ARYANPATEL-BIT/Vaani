/**
 * TapeBox -- the black live-tape box: a header line, the two track labels
 * (hidden on a phone) and the canvas that useStudioTape.js draws on.
 *
 * The canvas is decoration (aria-hidden): the state and the words it
 * pictures are already in the status word and the Script.
 */

import { memo } from 'react';
import { MODES, PERSONAS, REPLY_LANGUAGES, TEXT, VIEWS } from './talkContent.js';

const labelOf = (list, id) => list.find((x) => x.id === id)?.label ?? id;

function TapeBox({ view, persona, mode, language, canvasRef }) {
  return (
    <section className="tk-tape" aria-label={TEXT.tapeTitle}>
      <div className="tk-mono tk-tape-head">
        <span className="tk-tape-title">
          <span className="tk-ring" aria-hidden="true" />
          {TEXT.tapeTitle} · {VIEWS[view].tape}
        </span>
        <span className="tk-wide-only tk-tape-meta">
          {labelOf(PERSONAS, persona)} · {labelOf(MODES, mode)} · {labelOf(REPLY_LANGUAGES, language)}
        </span>
      </div>
      <div className="tk-tape-body">
        <div className="tk-mono tk-tracks tk-wide-only" aria-hidden="true">
          <span className="tk-track-ruler" />
          <span className="tk-track">{TEXT.trackVaani}</span>
          <span className="tk-track tk-track-you">{TEXT.trackYou}</span>
        </div>
        <canvas ref={canvasRef} className="tk-canvas" aria-hidden="true" />
      </div>
    </section>
  );
}

export default memo(TapeBox);
