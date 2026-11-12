/* global process */
/**
 * theme.test.js — the light/dark theme helper (theme.js).
 *
 * Covers:
 * 1. readStoredTheme: returns a valid stored value, null for nothing or
 *    junk, and null (not a crash) when storage throws, including when
 *    merely reaching window.localStorage throws.
 * 2. resolveTheme: a stored choice wins; with none, follow the system.
 * 3. applyTheme: sets data-theme on the root element.
 * 4. saveTheme: writes the value, and swallows a throwing storage.
 *
 * Storage is passed as a function that returns it, because in some
 * browsers the property access itself throws when site data is blocked.
 *
 * Run with:
 *   node frontend/src/theme/theme.test.js
 */

import {
  STORAGE_KEY, readStoredTheme, resolveTheme, applyTheme, saveTheme,
} from './theme.js';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${description}`);
  } else {
    failed += 1;
    console.error(`  FAIL ${description}`);
  }
}

/** A stand-in for window.localStorage backed by a plain object. */
function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value); },
  };
}

/** Storage whose methods throw, like a full or locked store. */
const brokenStorage = {
  getItem: () => { throw new Error('SecurityError'); },
  setItem: () => { throw new Error('QuotaExceededError'); },
};

/** Reaching the storage at all throws, like Chrome with site data blocked. */
const unreachable = () => { throw new Error('SecurityError'); };

console.log('readStoredTheme');
assert('key is vaani-theme', STORAGE_KEY === 'vaani-theme');
assert('stored dark -> dark', readStoredTheme(() => fakeStorage({ 'vaani-theme': 'dark' })) === 'dark');
assert('stored light -> light', readStoredTheme(() => fakeStorage({ 'vaani-theme': 'light' })) === 'light');
assert('nothing stored -> null', readStoredTheme(() => fakeStorage()) === null);
assert('junk stored -> null', readStoredTheme(() => fakeStorage({ 'vaani-theme': 'purple' })) === null);
assert('throwing storage -> null, no crash', readStoredTheme(() => brokenStorage) === null);
assert('unreachable storage -> null, no crash', readStoredTheme(unreachable) === null);

console.log('resolveTheme');
assert('stored dark beats light system', resolveTheme('dark', false) === 'dark');
assert('stored light beats dark system', resolveTheme('light', true) === 'light');
assert('no choice + dark system -> dark', resolveTheme(null, true) === 'dark');
assert('no choice + light system -> light', resolveTheme(null, false) === 'light');

console.log('applyTheme');
const root = { dataset: {} };
applyTheme('dark', root);
assert('sets data-theme=dark', root.dataset.theme === 'dark');
applyTheme('light', root);
assert('sets data-theme=light', root.dataset.theme === 'light');

console.log('saveTheme');
const storage = fakeStorage();
saveTheme('dark', () => storage);
assert('writes the value under the key', storage.data['vaani-theme'] === 'dark');
let threw = false;
try { saveTheme('dark', () => brokenStorage); } catch { threw = true; }
assert('throwing storage does not crash', threw === false);
threw = false;
try { saveTheme('dark', unreachable); } catch { threw = true; }
assert('unreachable storage does not crash', threw === false);

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
