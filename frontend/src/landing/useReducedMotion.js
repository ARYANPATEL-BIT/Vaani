/**
 * useReducedMotion -- true when the visitor has asked their operating system
 * for less motion (the CSS media query prefers-reduced-motion: reduce).
 *
 * useSyncExternalStore reads a value that lives outside React (here, the
 * browser's media query) and re-renders when it changes, so turning the
 * setting on while the page is open stops the animations at once.
 */

import { useSyncExternalStore } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

function subscribe(onChange) {
  const mql = window.matchMedia(QUERY);
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

function getSnapshot() {
  return window.matchMedia(QUERY).matches;
}

export default function useReducedMotion() {
  return useSyncExternalStore(subscribe, getSnapshot);
}
