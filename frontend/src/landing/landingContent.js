/**
 * landingContent.js -- every word, colour, link and timing on the landing page.
 *
 * The section components only lay this out. To change the copy, the accent,
 * the demo script or the measured latency, change it here and nowhere else.
 */

// The voice app. Every "Open the app" / "Start talking" button goes here.
export const APP_PATH = '/talk';

// The accent used for slashes, dots, the step kind and the "ms" label.
export const ACCENT = '#A99BFF';
// Demo-card dot colours that are not the accent.
export const CUT_COLOUR = '#FBBF24';
export const THINK_COLOUR = '#A3A3BA';

// Section links in the header and the footer. They are in-page anchors.
export const NAV_LINKS = [
  { href: '#what', label: 'What it is' },
  { href: '#interrupt', label: 'Interrupting' },
  { href: '#pipeline', label: 'How it works' },
  { href: '#latency', label: 'Latency' },
];

export const HERO = {
  words: ['SPEAK', 'Interrupt', 'LISTEN'],
  description:
    'A voice agent you can interrupt mid-sentence. It goes quiet the moment you speak, then listens to what you say next.',
  cta: 'Start talking',
  openApp: 'Open the app',
  pause: 'Pause animation',
  play: 'Play animation',
};

// The scripted demo card. Times are seconds into one loop. The wave reads
// the same timeline, so the ribbons swell and flatten in step with the text.
export const DEMO = {
  badge: 'Scripted demo',
  lines: {
    vaani: 'Sure. First rinse one cup of lentils, then heat the',
    user: "Wait, I don't have a pressure cooker.",
    reply: 'No problem. A covered pot works too. It just takes a little longer.',
  },
  timeline: {
    vaaniStart: 0.5, vaaniTyping: 4.3, // first answer types out
    cut: 4.9,                          // the user cuts in: playback stops
    userStart: 5.3, userTyping: 1.9,   // what the user said
    listen: 5.5,                       // from here: listening
    think: 7.6,                        // from here: thinking
    replyStart: 8.4, replyTyping: 3.1, // the new answer types out
    idle: 11.7,                        // from here: "Your turn"
    flashEnd: 5.7,                     // the white cut line has faded by here
    loop: 14,                          // then it starts again
  },
  // Reduced motion shows this one moment, with the whole transcript.
  stillFrameAt: 11.6,
  labels: {
    speak: 'Now speaking',
    cut: 'Interrupted, playback stopped',
    listen: 'Listening to you',
    think: 'Thinking',
    idle: 'Your turn',
  },
};

// The hero wave. Amplitude 0 is flat, 1 is full.
export const WAVE = {
  amplitude: { speak: 1, cut: 0.05, listen: 0.4, think: 0.24, idle: 0.3 },
  easeCut: 0.3,      // fraction of the gap closed per 60 Hz frame on a cut
  easeOther: 0.05,   // ... and in every other phase
  maxDpr: 2,         // never draw more than 2 canvas pixels per CSS pixel
  maxCanvasPx: 3400, // and never more than this many pixels across
  maxStepS: 0.05,    // a long gap between frames counts as at most this
};

export const PRELOADER = {
  label: 'Tuning in',
  countS: 2.7,       // the counter reaches 100 after this long
  fadeStartS: 2.9,   // the overlay starts to lift away
  fadeS: 0.8,        // and is gone this long after
  leadS: 3.1,        // the headline words start rising after this
  sessionKey: 'vaani-landing-preloader',
};

export const WHAT = {
  eyebrow: 'What it is',
  title: ['A voice agent that keeps ', 'listening', ' even while it talks.'],
  cards: [
    { num: '01', kind: 'speak', name: 'It speaks', text: 'Replies arrive as a stream and play as they come.' },
    { num: '02', kind: 'cut', name: 'You cut in', text: 'Start talking and playback stops at once.' },
    { num: '03', kind: 'listen', name: 'It listens', text: 'Then it answers what you actually said.' },
  ],
};

export const INTERRUPT = {
  eyebrow: 'Interrupting',
  title: ['Silence first. ', 'Everything else after.'],
  intro:
    'When you speak over Vaani, three things happen in a fixed order. You hear it stop before the system has finished cleaning up.',
  steps: [
    { num: '01', name: 'It hears you start', text: 'Speech detection runs on the CPU. Nothing on this path makes a network call, so noticing you never waits on the internet.' },
    { num: '02', name: 'Playback is flushed', text: 'The audio already queued in your browser is thrown away first. That is the moment the voice goes quiet.' },
    { num: '03', name: 'The work is cancelled', text: 'One cancel signal stops the speech synthesis and closes the stream from the language model, so nothing keeps running in the background.' },
  ],
  link: { href: '#pipeline', label: 'See the pipeline' },
};

export const PIPELINE = {
  eyebrow: 'How it works',
  title: ['Five steps between your voice and ', 'its reply.'],
  advanceS: 5, // auto-advance to the next step after this long
  steps: [
    { kind: 'Capture', name: 'Your microphone', short: 'Audio leaves your browser in tiny frames.', text: 'The browser cuts your voice into 20 millisecond frames and sends them to the gateway over a WebSocket while you speak.' },
    { kind: 'Detect', name: 'Silero VAD', short: 'Knows when you start and stop.', text: 'A small model on the CPU decides when you started and stopped talking. Nothing on this step touches the network.' },
    { kind: 'Transcribe', name: 'faster-whisper', short: 'Speech becomes text.', text: 'Turns what you said into text. The default setup runs it on the CPU, so no graphics card is needed.' },
    { kind: 'Think', name: 'Groq, with Gemini as backup', short: 'A hosted model writes the reply.', text: 'A hosted language model writes the reply as a stream. If the first provider fails, the second takes over.' },
    { kind: 'Speak', name: 'Piper', short: 'The reply becomes a voice.', text: 'Turns the reply into spoken audio and sends it to your browser to play. Interrupt it, and this is what stops.' },
  ],
};

export const LATENCY = {
  eyebrow: 'The quality bar',
  title: ['Fast enough to ', 'interrupt.'],
  text: 'Latency is the main measure of quality. The goal is a median under one second from the moment you stop talking to the first sound you hear.',
  chips: ['Interruptible', 'CPU first', 'Cancellable', 'Spend-capped'],
  targetLabel: 'Target, mic stop to first sound',
  target: '<1,000', // the project's stated target (CLAUDE.md), not a measurement
  unit: 'ms',
  // The measured P50 in ms. null until a real run is recorded; the page then
  // shows a marked placeholder. Put the number here, with its run file.
  measuredP50Ms: null,
  measuredSource: '', // e.g. 'docs/findings/<run file>.md'
  principles: [
    { icon: 'cpu', name: 'Runs on a CPU', text: 'The default setup needs no graphics card. A GPU is an option, not a requirement.' },
    { icon: 'stop', name: 'Everything can be cancelled', text: 'Every model call and long task carries a stop signal, and stopping closes the network stream cleanly.' },
    { icon: 'sliders', name: 'Vendors are settings', text: 'Model providers sit behind one adapter and are chosen in configuration, so swapping one never means rewriting the app.' },
    { icon: 'shield', name: 'Spend is capped', text: 'The spending limit is checked before any paid call is sent, not after the bill arrives.' },
  ],
};

export const CLOSING = {
  title: ['Say something. Then ', 'change your mind', ' halfway.'],
  text: 'Start a conversation, and interrupt whenever you like.',
  cta: 'Start a conversation',
};

export const FOOTER = {
  name: 'Vaani',
  nameHindi: '\u0935\u093E\u0923\u0940', // the word Vaani in Devanagari
  tagline: 'A real-time voice agent you can interrupt.',
  exploreLabel: 'Explore',
  builtByLabel: 'Built by',
  builtBy: 'Aryan and Samyak',
};
