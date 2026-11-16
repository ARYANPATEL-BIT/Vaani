/**
 * StudioErrorBanner -- the old conversation page's error banner, restyled.
 * Same three cases, same titles, same text (the hook's errorMessage), same
 * buttons, same role="alert" (a live region read out at once).
 */

import { ERRORS } from './talkContent.js';

export default function StudioErrorBanner({ errorMessage, isMicDenied, isConnectionDropped, isCapturing, onRetry, onDismiss }) {
  if (!errorMessage) return null;
  const title = isMicDenied
    ? ERRORS.micDenied
    : isConnectionDropped
    ? ERRORS.dropped
    : ERRORS.service;
  return (
    <div className="tk-error" role="alert">
      <div className="tk-error-text">
        <strong className="tk-mono tk-error-title">{title}</strong>
        <p>{errorMessage}</p>
      </div>
      <div className="tk-error-actions">
        {isMicDenied && (
          <button type="button" className="tk-mono tk-pill" onClick={onRetry}>{ERRORS.tryAgain}</button>
        )}
        {isConnectionDropped && !isCapturing && (
          <button type="button" className="tk-mono tk-pill" onClick={onRetry}>{ERRORS.reconnect}</button>
        )}
        <button type="button" className="tk-mono tk-pill" onClick={onDismiss} aria-label={ERRORS.dismissLabel}>
          {ERRORS.dismiss}
        </button>
      </div>
    </div>
  );
}
