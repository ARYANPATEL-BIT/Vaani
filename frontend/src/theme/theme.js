/**
 * theme.js — which colour theme (light or dark) the app shows.
 *
 * The theme is one attribute on <html>: data-theme="light" or "dark".
 * theme/colors.css defines every colour that differs between the themes as
 * a CSS variable on :root and overrides it under [data-theme="dark"], so
 * flipping the attribute recolours the whole app at once.
 *
 * The user's choice lives in localStorage under STORAGE_KEY. With no stored
 * choice, the operating system's light/dark setting decides.
 *
 * KEEP IN SYNC: index.html has a tiny inline copy of readStoredTheme +
 * resolveTheme + applyTheme. It must run before React loads (so the first
 * paint is already the right theme) and cannot import this module.
 *
 * getStorage is a function returning the storage, not the storage itself:
 * in some browsers merely reading window.localStorage throws when site data
 * is blocked, and that read has to happen inside the try. The root element
 * is passed in too, so node can test all of this (theme.test.js).
 */

export const STORAGE_KEY = 'vaani-theme';

/** The stored choice, or null if there is none, it is junk, or storage throws. */
export function readStoredTheme(getStorage) {
  try {
    const value = getStorage().getItem(STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

/** A stored choice wins; otherwise follow the system setting. */
export function resolveTheme(stored, prefersDark) {
  return stored ?? (prefersDark ? 'dark' : 'light');
}

/** Show `theme` by setting data-theme on the root element (<html>). */
export function applyTheme(theme, root) {
  root.dataset.theme = theme;
}

/** Remember the choice. If storage throws, the choice lasts this page load only. */
export function saveTheme(theme, getStorage) {
  try {
    getStorage().setItem(STORAGE_KEY, theme);
  } catch {
    // Nothing to do: the theme is already applied, it just won't persist.
  }
}
