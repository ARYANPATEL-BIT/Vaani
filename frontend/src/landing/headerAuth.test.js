/* global process */
/**
 * headerAuth.test.js -- the landing header's sign-in corner, RENDERED.
 *
 * loginState.test.js checks the state (landingAuthFor); this checks what the
 * visitor would see for it: the real HeaderAuth.jsx turned into HTML in Node.
 *
 * How: JSX is not plain JavaScript, so Node cannot import a .jsx file. Vite
 * (already the dev server and build tool) can: createServer in middleware
 * mode reads vite.config.js (with the React plugin that compiles JSX), and
 * ssrLoadModule compiles and loads one file the way the server-side
 * rendering path would. react-dom/server's renderToStaticMarkup then gives
 * the HTML. A MemoryRouter supplies the router that <Link> needs. No browser,
 * no new dependency.
 *
 * Run with:
 *   node frontend/src/landing/headerAuth.test.js   (from frontend/: npm test)
 */

import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

let passed = 0;
let failed = 0;

function assert(description, condition) {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${description}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${description}`);
  }
}

const vite = await createServer({
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'silent',
});

try {
  const { default: HeaderAuth } = await vite.ssrLoadModule('/src/landing/HeaderAuth.jsx');
  const { landingAuthFor } = await vite.ssrLoadModule('/src/login/loginState.js');

  // The header for one /auth/me answer, as HTML.
  const header = (status, body) => renderToStaticMarkup(
    createElement(MemoryRouter, null,
      createElement(HeaderAuth, { auth: landingAuthFor(status, body), onLogOut: () => {} })),
  );

  console.log('signed out (401)');
  const out = header(401, null);
  assert('a Sign in link to /login', /<a[^>]*href="\/login"[^>]*>Sign in<\/a>/.test(out));
  assert('no Log out button', !out.includes('Log out'));

  console.log('backend down (the dev proxy\'s 502) or no answer');
  for (const status of [502, null]) {
    assert(`${status}: a Sign in link`, header(status, null).includes('>Sign in</a>'));
  }

  console.log('signed in (200 with a name)');
  const signedIn = header(200, { email: 'a@b.c', name: 'Aryan Patel' });
  assert('the first name', signedIn.includes('Aryan') && !signedIn.includes('Patel'));
  assert('a visible Log out button', /<button[^>]*type="button"[^>]*>Log out<\/button>/.test(signedIn));
  assert('no Sign in link', !signedIn.includes('Sign in'));

  console.log('auth off (200, email null)');
  assert('nothing at all', header(200, { email: null, name: null }) === '');
} finally {
  await vite.close();
}

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
