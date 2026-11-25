/**
 * landingContent.js -- every word, colour, link, timing and image on the
 * landing page ("On Air" design, docs/design/landing-on-air/).
 *
 * The section components only lay this out. To change the copy, a colour,
 * the demo script or the measured latency, change it here and nowhere else.
 *
 * Images use `new URL('./assets/x.webp', import.meta.url).href` instead of
 * `import x from ...`: Vite still swaps in the fingerprinted file at build
 * time, but plain Node (demoScript.test.js imports this file) just sees a
 * string and does not try to load an image as JavaScript.
 */

const img = (name) => new URL(`./assets/${name}`, import.meta.url).href;

// The voice app. Every "Open the app" / "Start talking" link goes here.
export const APP_PATH = '/talk';

// The palette. LandingPage.jsx turns each entry into a CSS variable
// (--lp-paper, --lp-ink, ...) and the stylesheets only use the variables.
export const PALETTE = {
  paper: '#EEE9DF',
  paperDeep: '#E4DDD0',  // the voices section
  ink: '#141312',
  tape: '#1A1816',       // the tape and the monitor
  tapeLine: '#34302B',
  tapeTrack: '#24211E',
  red: '#FF3B1C',        // fills, lines, and red text on ink (about 5.2:1)
  // #FF3B1C on paper is only about 2.9:1, too low for text. Red text on
  // paper uses this deeper red instead (about 5.3:1 on paper, 4.7:1 on
  // paperDeep). See docs/learning/frontend-learning/21-landing-on-air.md.
  redText: '#B8240A',
  muted: '#5E5950',      // secondary text on paper
  mutedInk: '#A39D92',   // secondary text on ink
  softInk: '#C9C3B8',    // nav links on ink
  faint: '#8A847A',      // inactive big step numbers on paper (3:1, large text)
  rule: '#CFC6B6',
  dim: '#4A453F',
  footerMark: '#2A2724',
  dial: '#EEE3D0',       // the radio's dial panel (ink and redText sit on it)
  pulse: 'rgba(255, 59, 28, 0.55)', // the grille's pulse ring (red, see-through)
};

export const IMAGES = {
  portrait: img('portrait.webp'),
  reel: img('reel.webp'),
  chai: img('chai.webp'),
  notebook: img('notebook.webp'),
  spanner: img('spanner.webp'),
  radio: img('radio.webp'),
  cursor: img('cursor.png'),
};
// The scissors cursor's hotspot: the pixel (from the top-left of
// cursor.png) that is the actual click point.
export const CURSOR_HOTSPOT = { x: 5, y: 2 };

export const BRAND = {
  hindi: 'वाणी', // the word Vaani in Devanagari
  hindiWord: 'हिन्दी', // "Hindi" in Devanagari
};

// Section links in the floating nav and the footer (in-page anchors).
export const NAV_LINKS = [
  { href: '#idea', label: 'Idea' },
  { href: '#cut', label: 'Cut in' },
  { href: '#voices', label: 'Voices' },
  { href: '#chain', label: 'Signal chain' },
  { href: '#latency', label: 'Latency' },
];

export const CLOCK = { timeZone: 'Asia/Kolkata', label: 'IST', everyMs: 15000 };

export const PRELOADER = {
  label: 'Tuning in',
  countS: 1.8,      // the counter reaches 100 after this long
  liftStartS: 1.9,  // the panel starts to lift away
  liftS: 0.9,       // and is gone this long after
  leadS: 2.2,       // the headline letters start rising after this
  sessionKey: 'vaani-landing-preloader',
};

export const HERO = {
  onAir: 'On air',
  openApp: 'Open the app',
  signIn: 'Sign in',        // shown only to a signed-out visitor; no Sign up: access is by allowlist
  signedInAs: 'Signed in as', // read by screen readers before the first name
  backToTop: 'Vaani, back to top',
  fileLabel: 'File 001 — a real-time voice agent',
  languages: 'Hindi · English · Hinglish',
  headline: ['TALK', 'OVER', 'IT.'],
  headlineSpoken: 'Talk over it.',
  redChars: '.',          // characters drawn in red
  letterStepS: 0.045,     // each letter rises this long after the previous one
  description:
    'Vaani stops mid-word the moment you start speaking, throws away what it was about to say, and answers what you actually said.',
  cta: 'Start talking',
};

// The scripted demo on the tape. All times in seconds. Times after the cut
// are measured from the cut, so moving the cut moves everything after it.
export const DEMO = {
  title: 'Live tape',
  badge: 'Scripted demo · no microphone',
  tracks: ['01 Vaani', '02 You'],
  speakers: { vaani: 'Vaani', user: 'You' },
  lines: {
    vaani: 'Sure. First rinse one cup of lentils, then heat the',
    user: 'Wait, I don’t have a pressure cooker.',
    reply: 'No problem. A covered pot works too. It just takes a little longer.',
  },
  timeline: {
    vaaniStart: 0.5, vaaniTyping: 4.3, // the first answer types out
    defaultCut: 4.8,   // where the cut falls if nobody presses Cut in
    earliestCut: 0.8,  // Cut in is enabled from here until the cut
    userDelay: 0.4, userTyping: 1.9,   // the user's line, after the cut
    thinkDelay: 2.3,   // from cut + this: thinking
    replyDelay: 3.1, replyTyping: 3.2, // the new answer, after the cut
    idleDelay: 6.3,    // from cut + this: "your turn"
    loopTail: 8.6,     // the loop restarts at cut + this
    flashS: 0.45,      // the red flash on the cut fades over this long
  },
  stillFrameAt: 11.15, // reduced motion shows this moment (default cut)
  labels: {
    idle: 'your turn',
    speak: 'Vaani is speaking',
    cut: 'cut — playback flushed',
    you: 'listening to you',
    think: 'thinking',
    reply: 'answering what you said',
  },
  hints: {
    reduced: 'Motion is reduced. This is the finished exchange.',
    cutDone: 'You cut it off mid-word. Now try it with your voice.',
    canCut: 'Press while Vaani is speaking.',
    waiting: 'It stops the moment you speak.',
  },
  cutButton: 'Cut in',
  cutLabel: 'Cut in: interrupt Vaani',
  pause: 'Pause',
  play: 'Play',
};

// The tape canvas (drawTape.js).
export const TAPE = {
  heightPx: 250,
  playheadAt: 0.64,                 // the playhead sits at 64% of the width
  speedPxPerS: { min: 48, max: 110, perWidth: 1 / 9 }, // scroll speed
  barGapPx: 5, barWidthPx: 3,       // one bar every 5 px of tape
  maxDpr: 2,                        // never more than 2 canvas px per CSS px
  maxCanvasPx: 3400,                // ... nor this many pixels across
  maxStepS: 0.05,                   // a long gap between frames counts as this
  fadePx: 70,                       // old tape fades out on the left
  colours: {
    future: 'rgba(0,0,0,0.22)', divider: '#34302B', baseline: '#2C2925',
    ticks: '#A39D92', vaani: '238,233,223', playhead: '#EEE9DF',
    cutText: '#141312', fade: '26,24,22',
  },
};

export const SPECS = [
  { num: '3', unit: 'voices', label: 'Default, Tutor, Support' },
  { num: '2', unit: 'languages', label: 'Hindi and English, mixed freely' },
  { num: '20', unit: 'ms', label: 'Audio frame sent while you speak' },
  { num: '1', unit: 'signal', label: 'Cancels everything on interrupt' },
  { num: '<1,000', unit: 'ms', label: 'Target, mic stop to first sound' },
];

export const CUT_BAND = {
  eyebrow: 'The moment',
  title: ['Say ', '“wait”', '.'], // the middle part is red
  text: 'Vaani hears you in the middle of its own sentence, and stops right there.',
  alt: 'Illustration of a young woman in a red kurta, mid-word, raising her hand as if to say wait.',
  tag: 'Cut 00:04.80',
};

export const TICKER = [
  'Interrupt any time', '<hindi>', 'English', 'Hinglish', 'Runs on a CPU',
  'Every call can be cancelled', 'Spend-capped', 'Three voices',
];

export const IDEA = {
  eyebrow: '01 — The idea',
  text: 'Most voice assistants wait for their turn. Vaani doesn’t need one. Start talking and it goes quiet mid-word, throws away what it was about to say, and listens to what you actually meant.',
  redWords: ['goes', 'quiet', 'mid-word,'],
  // Word i lights up over [start + i/n * span, + width] % of the section's
  // pass through the screen ("cover" range of its view timeline).
  range: { start: 18, span: 38, width: 7 },
};

export const STORY = {
  title: 'When you cut in',
  eyebrow: '02 — Three things, in a fixed order',
  monitor: 'Monitor',
  steps: [
    { name: 'It hears you start', text: 'Speech detection runs on the CPU. Nothing on this path makes a network call, so noticing you never waits on the internet.', tag: 'Speech detected', note: 'Your voice appears on the mic lane. The detector notices on the CPU, with no network call in the way.' },
    { name: 'Playback is flushed', text: 'The audio already queued in your browser is thrown away first. That is the moment the voice goes quiet.', tag: 'Queue flushed', note: 'Everything Vaani had queued to play after the red line is dropped. You hear it stop here.' },
    { name: 'The work is cancelled', text: 'One cancel signal stops the speech synthesis and closes the stream from the language model, so nothing keeps running in the background.', tag: 'Cancel sent', note: 'The half-written reply and its synthesis are stopped by one signal, and the model stream is closed.' },
  ],
  // Monitor lanes: a solid block (a) and a dashed "dropped" block (b), in %
  // of the lane. `step` is the story step that lights the lane up.
  lanes: [
    { name: 'Mic', step: 0, a: [50, 50], b: null, tag: 'You' },
    { name: 'Playback', step: 1, a: [0, 50], b: [50, 46], tag: 'Flushed' },
    { name: 'Model + voice', step: 2, a: [0, 52], b: [52, 44], tag: 'Cancelled' },
  ],
  // The step whose box crosses the middle 10% of the screen is active.
  observerMargin: '-45% 0px -45% 0px',
};

// The three personas in backend/config.toml [personas].
export const VOICES = {
  eyebrow: '03 — Three voices, one speaker each in English and ',
  languages: 'English · ',
  talkTo: 'Talk to',
  rotateMs: 4500, // auto-advance until the visitor picks one
  bars: 36,       // waveform bars on the card
  list: [
    { name: 'Default', img: IMAGES.chai, motion: 'float', seed: 1.3, mood: 'Friendly, for everyday questions.', text: 'A general voice assistant. Ask about anything, change the subject, or cut it off and ask again.' },
    { name: 'Tutor', img: IMAGES.notebook, motion: 'tilt', seed: 2.9, mood: 'Patient, and checks you followed.', text: 'Explains step by step and asks whether it made sense before moving on. Interrupt with a question any time.' },
    { name: 'Support', img: IMAGES.spanner, motion: 'twist', seed: 4.7, mood: 'Short, practical answers.', text: 'Gets to the point and keeps replies brief, for when you want the fix and not the lecture.' },
  ],
};

export const CHAIN = {
  title: 'Signal chain',
  text: 'Five steps between your voice and its reply. Interrupt anywhere, and one cancel signal runs back up the chain.',
  steps: [
    { kind: 'Capture', name: 'Your browser', text: 'Your voice leaves the browser in 20 millisecond frames over a WebSocket while you speak.' },
    { kind: 'Detect', name: 'Silero VAD', text: 'A small model on the CPU decides when you started and stopped talking.' },
    { kind: 'Transcribe', name: 'faster-whisper', text: 'Turns what you said into text. The default setup runs it on the CPU.' },
    { kind: 'Think', name: 'Groq › Gemini', text: 'A hosted model writes the reply as a stream. If the first provider fails, the second takes over.' },
    { kind: 'Speak', name: 'Piper', text: 'Turns the reply into a voice for your browser to play. Interrupt it, and this is what stops.' },
  ],
};

export const LATENCY = {
  eyebrow: '05 — The quality bar',
  target: '1,000',  // the project's stated target (CLAUDE.md), not a measurement
  targetSpoken: 'Under 1,000 milliseconds',
  unit: 'ms',
  caption: 'Target · median · from the moment you stop talking to the first sound you hear',
  // The measured P50 in ms. null until a real run is recorded; the page then
  // says "not yet measured". Put the number here, with its run file.
  measuredP50Ms: null,
  measuredSource: '', // e.g. 'docs/findings/<run file>.md'
  notMeasured: 'Not yet measured end to end. This is the target, not a result.',
  measured: 'Measured median', // shown as "Measured median: 870 ms (source)"
  // Digit i rolls over [cover from+i*step %, cover to+i*step %] of the
  // number's trip through the screen, so it lands while still well in view.
  roll: { from: 10, to: 40, step: 4 },
  rules: [
    { n: 'A', name: 'Runs on a CPU', text: 'The default setup needs no graphics card. A GPU is an option, not a requirement.' },
    { n: 'B', name: 'Everything can be cancelled', text: 'Every model call and long task carries a stop signal, and stopping closes the network stream cleanly.' },
    { n: 'C', name: 'Vendors are settings', text: 'Model providers sit behind one adapter and are chosen in configuration.' },
    { n: 'D', name: 'Spend is capped', text: 'The spending limit is checked before any paid call is sent, not after the bill arrives.' },
  ],
};

// The radio is the closing link. Every overlay position is a percentage of
// the radio image's box (radio.webp, 640 x 431), measured on the dial window
// and the speaker grille, so the overlays stay on them at any width.
export const CLOSING = {
  text: 'Say something. Then change your mind halfway.',
  ariaLabel: 'Start talking: open the Vaani app',
  label: ['Start', 'talking ↗'], // two lines on the dial
  smallLink: 'or open the app →',
  dial: { left: 52.1, top: 38.9, width: 28.9, height: 18.5 },
  grille: { left: 16.1, top: 32.7, width: 33.8 },
  // The radio itself inside the image's transparent margins (measured from
  // the alpha channel). The box is sized so this part fills the column, and
  // the focus ring is drawn around it, not around the margins.
  visible: { left: 11.6, top: 3.7, width: 76.4, height: 92.3 },
  imagePx: { width: 640, height: 431 }, // radio.webp; the box keeps this shape
  maxBoxPx: 760, // desktop cap: the visible radio is then about 580 px wide
  // The label font follows the radio box: phone size at a 450 px box,
  // desktop size at a 760 px box, a straight line between.
  labelPx: { atBox: [450, 760], size: [19, 37] },
};

export const FOOTER = {
  tagline: 'A real-time voice agent you can interrupt.',
  builtBy: 'Built by Aryan and Samyak',
};
