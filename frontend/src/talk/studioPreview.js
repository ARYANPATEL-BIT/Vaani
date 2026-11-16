/**
 * studioPreview.js -- DEVELOPMENT ONLY. Sample data so the design of the
 * live states can be reviewed without a backend: open
 *   /talk?preview=listening | thinking | speaking | cut
 *
 * StudioPage.jsx calls previewFor() only inside `import.meta.env.DEV ? ... :
 * null`. In a production build Vite replaces import.meta.env.DEV with
 * false, so that branch, this module and its sample text are dropped from
 * the bundle. It never touches a hook: it only replaces the values the page
 * would otherwise read from them.
 *
 * The sample conversation is placeholder text from the design mockups.
 */

const t0 = Date.now();
const at = (s) => t0 + s * 1000;

const BASE = [
  { id: 'p1', role: 'user', text: 'Namaste! Kya tum Hindi samajhte ho?', timestamp: at(1) },
  { id: 'p2', role: 'agent', text: 'Haan, bilkul. Aap Hindi, English ya dono mein baat kar sakte hain.', timestamp: at(2.4), interrupted: false },
];
const QUESTION = { id: 'p3', role: 'user', text: 'Dal kaise banate hain without a pressure cooker?', timestamp: at(5.2) };
const REPLY = 'Bilkul. Rinse one cup of toor dal, soak it for twenty minutes, then simmer it with turmeric and salt.';

// Fake levels: a wobbling loudness while a track is "talking", else 0.
const wobble = (seed) => () => {
  const t = performance.now() / 1000;
  return 0.03 + 0.05 * Math.abs(Math.sin(t * 7.3 + seed) * Math.sin(t * 2.1 + seed * 3));
};
const silent = () => 0;

const SCENES = {
  listening: {
    turnState: 'listening',
    entries: BASE,
    partialUser: 'Dal kaise banate hain without a',
    readMic: wobble(1),
    readPlayback: silent,
  },
  thinking: {
    turnState: 'thinking',
    entries: [...BASE, QUESTION],
    readMic: silent,
    readPlayback: silent,
  },
  speaking: {
    turnState: 'speaking',
    entries: [...BASE, QUESTION],
    agentPartial: REPLY,
    readMic: silent,
    readPlayback: wobble(2),
  },
  cut: {
    turnState: 'listening',
    cut: true,
    entries: [...BASE, QUESTION,
      { id: 'p4', role: 'agent', text: 'Bilkul. Rinse the toor dal, soak it', timestamp: at(7.4), interrupted: true }],
    partialUser: 'Wait, I only have moong dal. Does that',
    readMic: wobble(3),
    readPlayback: silent,
  },
};

/** The scene for ?preview=<name>, or null. */
export function previewFor(name) {
  const scene = SCENES[name];
  if (!scene) return null;
  return { partialUser: null, agentPartial: null, cut: false, startWall: t0, ...scene };
}
