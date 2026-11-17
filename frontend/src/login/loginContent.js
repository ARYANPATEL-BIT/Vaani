/**
 * loginContent.js -- every word and colour on the /login page, from the
 * design in docs/design/login-studio-door/. Components only read from here.
 *
 * Colours are the Studio's PAPER values (talk/talkContent.js): the login page
 * is the studio's front door, so it uses the same paper, ink and red.
 */

export const COLORS = {
  '--lg-bg': '#EEE9DF',
  '--lg-text': '#141312',
  '--lg-body': '#3D3A35',     // paragraph text on paper
  '--lg-muted': '#5E5950',    // labels on paper (5.75:1)
  '--lg-faint': '#8A8478',    // the smallest hints
  '--lg-red': '#FF3B1C',      // fills only: lamp, dots, the studio button
  '--lg-red-text': '#B8240A', // red TEXT on paper; #FF3B1C is only ~2.9:1 there
  '--lg-card': '#F6F2EA',     // the alert box
  '--lg-door': '#141312',     // the black studio door
  '--lg-door-text': '#EEE9DF',
  '--lg-door-muted': '#A39D92',
  '--lg-door-faint': '#6E685F',
  '--lg-door-rule': '#2E2B27',
  '--lg-lamp': '#1F1D1A',     // the unlit lamp's glass
  '--lg-lamp-edge': '#3A3631',
  '--lg-lamp-word': '#5E5950', // the unlit "On air" outline
};

export const TEXT = {
  file: 'File 000 — sign in',
  back: '← Back to the landing page',
  backShort: '← Home',
  clock: 'IST',
  room: 'Room 01 · Vaani',
  timecode: '00:00.00',
  title: ['Sign in', 'to go', 'on air.'],
  intro: 'Vaani is invite-only while we build it. Use the Google account that is on the guest list. The mic stays off until you are in.',
  introShort: 'Invite-only while we build it. Use the Google account on the guest list.',
  checking: 'Google said yes. Now checking your name against the guest list',
  checkingButton: 'Checking your pass',
  onAir: ["You're in, ", '. Opening the studio'],
  goToStudio: 'Go to the studio →',
  facts: ['Invite-only guest list', 'Stays signed in for 7 days', 'Sign out from the rail any time'],
  footer: ['Signed by Google · session cookie, httpOnly', 'Vaani · CPU-first voice agent'],
  noClientId: 'Sign-in is not set up in this copy of the app: VITE_GOOGLE_CLIENT_ID is empty in frontend/.env.local.',
  googleFailed: "Google's sign-in button did not load. Check your connection and reload the page.",
  doorLabel: 'Studio door',
  lampOff: 'On-air lamp, off',
  lampOn: 'On-air lamp, lit',
};

/** Per view: the door's status, the mic line, the step and the button hint. */
export const VIEWS = {
  off: { door: 'standby', mic: '01 You · mic off until you sign in', step: 'Studio access · step 1 of 2', hint: "Google's own button, rendered by Google", hintShort: "Google's own button · stays signed in 7 days" },
  checking: { door: 'checking pass', mic: '01 You · mic off · checking', step: 'Studio access · step 2 of 2', hint: 'Button locked so you cannot sign in twice' },
  refused: { door: 'refused', mic: '01 You · mic stays off', step: 'Studio access · step 1 of 2', hint: "Opens Google's account picker" },
  error: { door: 'no line', mic: '01 You · mic stays off', step: 'Studio access · step 1 of 2', hint: "Google's own button, rendered by Google" },
  onair: { door: 'on air', mic: '01 You · mic ready', step: 'Studio access · step 2 of 2' },
};

/** The alert box, per reason from loginState.js. */
export const ALERTS = {
  notAllowed: { tag: '403 · not on the list', title: "This account isn't invited.", text: "Google signed you in, but this email is not on Vaani's guest list. Try another account, or ask the team to add this one." },
  unverified: { tag: '403 · email not verified', title: "This email isn't verified.", text: "Google hasn't confirmed this address. Verify it with Google, or use another account." },
  invalidToken: { tag: '401 · token rejected', title: "Google's answer didn't check out.", text: 'The sign-in expired or was cut short. Try again.' },
  googleDown: { tag: '503 · Google unreachable', title: "Couldn't reach Google.", text: 'Nothing is wrong with your account. Check your connection and try again.', door: 'no line to Google' },
  badOrigin: { tag: '403 · origin not allowed', title: "This address isn't allowed.", text: "The server doesn't accept sign-ins from this page's address." },
  serverDown: { tag: 'No answer · Vaani server', title: "Couldn't reach Vaani.", text: "The Vaani server isn't answering. Try again." },
};

/** Heights (px) of the mic line's bars when lit: a fixed, made-up pattern. */
export const BAR_COUNT = 120;
export const LIT_BARS = Array.from({ length: BAR_COUNT }, (_, i) =>
  Math.round(6 + 29 * Math.abs(Math.sin(i * 1.7) * Math.sin(i * 0.37 + 1))));
