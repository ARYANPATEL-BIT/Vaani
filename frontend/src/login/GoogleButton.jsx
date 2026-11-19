/**
 * GoogleButton -- Google's own "Sign in with Google" button.
 *
 * Google Identity Services (GIS) is a script Google hosts. Once loaded it
 * puts `window.google.accounts.id` on the page. We tell it our client ID and
 * a callback (initialize), then ask it to draw its button into our <div>
 * (renderButton). Google draws the button inside its own frame, so we cannot
 * restyle it: we choose only Google's presets (pill shape; the outline theme
 * on the light page, filled_black on the dark one).
 * When the user picks an account, Google calls our callback with an ID token
 * (a JWT signed by Google) in `response.credential`; the page sends that to
 * our backend. We never see a password, and the browser never needs a secret.
 *
 * The script is added once per page load with a plain <script> tag (no npm
 * package). The promise below is module-level so a second mount reuses it.
 */

import { useEffect, useRef, useState } from 'react';
import { GIS_SCRIPT_URL, GOOGLE_CLIENT_ID } from '../config.js';
import { TEXT } from './loginContent.js';

let gisPromise = null;

function loadGis() {
  if (!gisPromise) {
    gisPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = GIS_SCRIPT_URL;
      script.async = true;
      script.onload = () => resolve(window.google.accounts.id);
      script.onerror = () => {
        gisPromise = null; // let a later mount try again
        reject(new Error('GIS failed to load'));
      };
      document.head.appendChild(script);
    });
  }
  return gisPromise;
}

// Google accepts a button width from 200 to 400 px.
const clampWidth = (px) => Math.max(200, Math.min(400, Math.round(px)));

export default function GoogleButton({ onCredential }) {
  const boxRef = useRef(null);
  const [failed, setFailed] = useState(false);
  // The latest callback, read when Google calls back. GIS keeps the function
  // it was given at initialize; reading through a ref means it never calls a
  // stale one after the page re-renders.
  const onCredentialRef = useRef(onCredential);
  useEffect(() => { onCredentialRef.current = onCredential; });

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return undefined;
    let alive = true; // false after unmount: do not draw into a removed node
    loadGis().then((gis) => {
      if (!alive || !boxRef.current) return;
      gis.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => onCredentialRef.current(response.credential),
      });
      // The app's theme is on <html> (theme/theme.js); /login cannot change
      // it, so it is read once, when Google draws the button.
      const dark = document.documentElement.dataset.theme === 'dark';
      gis.renderButton(boxRef.current, {
        theme: dark ? 'filled_black' : 'outline', shape: 'pill', size: 'large', text: 'signin_with',
        width: clampWidth(boxRef.current.clientWidth),
      });
    }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, []);

  if (!GOOGLE_CLIENT_ID) return <p className="lg-note" role="alert">{TEXT.noClientId}</p>;
  if (failed) return <p className="lg-note" role="alert">{TEXT.googleFailed}</p>;
  return <div ref={boxRef} className="lg-gsi" />;
}
