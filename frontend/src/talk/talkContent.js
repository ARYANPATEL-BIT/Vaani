/**
 * talkContent.js -- every word, colour, size and timing of the Studio
 * conversation page (/talk). Components and CSS read from here; nothing in
 * them is hard-coded.
 *
 * StudioPage.jsx turns PAPER and INK into CSS variables (--tk-paper, ...):
 * PAPER is the normal theme, INK is used under data-theme="dark" (the app's
 * dark mode, called "Ink mode" here).
 */

export const PAPER = {
  bg: '#EEE9DF',
  text: '#141312',
  muted: '#5E5950',      // secondary text on paper (5.75:1)
  redText: '#B8240A',    // red text on paper; #FF3B1C is only ~2.9:1 there
  red: '#FF3B1C',        // fills: the Talk button, the needle, dots
  rule: '#CFC6B6',
  line: '#141312',       // the 1.5 px structural lines
  stroke: '#141312',     // outlined (not-final) words
  wash: 'rgba(255, 59, 28, 0.07)', // the live turn's faint red wash
  tapeBg: '#141312',
  tapeEdge: '#141312',
  onRed: '#141312',      // text and dots on the red buttons (5.2:1)
  backdrop: 'rgba(20, 19, 18, 0.55)', // behind an open sheet
  grain: '0.08',
};

export const INK = {
  bg: '#141312',
  text: '#EEE9DF',
  muted: '#A39D92',
  redText: '#FF3B1C',    // on ink the bright red passes (about 5.2:1)
  red: '#FF3B1C',
  rule: '#34302B',
  line: '#4A453F',
  stroke: '#EEE9DF',
  wash: 'rgba(255, 59, 28, 0.12)',
  tapeBg: '#0B0A09',     // darker than the page, so the box still reads
  tapeEdge: '#34302B',
  onRed: '#141312',
  backdrop: 'rgba(0, 0, 0, 0.6)',
  grain: '0.05',
};

// The tape box (canvas). Colours are the same in both themes: the box is
// always dark.
export const TAPE = {
  pxPerS: 66,            // one second of tape is 66 px wide at every width,
                         // so a narrow tape shows fewer seconds, not denser bars
  maxWindowS: 30,        // the longest tape kept in memory (a 1980 px canvas)
  headFrac: 0.75,        // the playhead stops here and the tape scrolls
  stepMs: 75,            // one bar (one level sample) every 75 ms
  barPx: 2.5,            // thin lines, as in the design
  levelGain: 1.7,        // bar height = min(1, sqrt(rms) * gain) of the track
  minLevel: 0.004,       // quieter than this draws nothing
  recentS: 0.45,         // the newest bars are drawn brighter
  reducedMotionMs: 500,  // under reduced motion, redraw twice a second
  maxDpr: 2,
  rulerPx: 24,
  colors: {
    rule: '#2E2B27',
    rulerText: '#A39D92',
    label: '#C9C3B8',      // the 01 Vaani track label
    vaani: '#7D776E',
    vaaniNow: '#EEE9DF',
    you: '#8E2717',
    youNow: '#FF3B1C',
    head: '#EEE9DF',
    cut: '#FF3B1C',
    cutText: '#141312',
  },
  font: '500 10px "Vaani Mono", ui-monospace, monospace',
  headFont: '12px "Vaani Mono", ui-monospace, monospace',
};

export const TEXT = {
  file: 'File 002 — conversation',
  title: 'Vaani',
  station: 'Station',
  replyGroup: 'Reply language',
  modeSwitch: 'Push-to-talk',
  lockedHint: 'Fixed for this session. End it to change.',
  settingsButton: 'Station and settings',
  settingsTitle: 'Settings',
  close: 'Close',
  tapeTitle: 'Live tape',
  trackVaani: '01 Vaani',
  trackYou: '02 You',
  script: 'Script',
  turns: (n) => `${String(n).padStart(2, '0')} turns`,
  you: 'You',
  vaani: 'Vaani',
  cutTag: 'Cut',
  liveTag: 'Live',
  latencyLabel: 'First sound · last turn',
  latencyEmpty: '---',
  latencyUnit: 'ms',
  latencyTarget: 'Target <1,000 ms',
  latencyNone: 'Not measured yet',
  latencyHas: 'From server telemetry',
  counter: 'Tape counter',
  talk: 'Talk',
  stop: 'Stop',
  end: 'End',
  tuning: 'Tuning…',
  scriptButton: 'Script',
  scriptDialog: 'Full script',
  placeholder: 'Say something',
  rail: {
    nav: 'App',
    home: 'Vaani home',
    talk: 'Talk',
    history: 'History (coming soon)',
    ink: 'Ink mode',
    paper: 'Paper mode',
    operator: 'Operator',
    signOut: 'Sign out',
  },
  aria: {
    connect: 'Connect and start voice session',
    end: 'End conversation session',
    speak: 'Start talking',
    stopTalking: 'Stop talking',
    showScript: 'Show the full script',
  },
};

// Personas of backend/config.toml [personas]. dialPct: where each sits on
// the station dial, in % of its width.
export const PERSONAS = [
  { id: 'default', label: 'Default', desc: 'Friendly voice assistant', dialPct: 16.5 },
  { id: 'tutor', label: 'Tutor', desc: 'Patient explanations & checks', dialPct: 50 },
  { id: 'support', label: 'Support', desc: 'Concise & practical help', dialPct: 83.5 },
];

// session.start's mode (docs/contracts.md §2.8).
export const MODES = [
  { id: 'vad', label: 'Hands-free', desc: 'Just talk; a pause ends your turn' },
  { id: 'ptt', label: 'Push-to-talk', desc: 'Press Talk or hold Space to talk' },
];

// session.start's reply_language (docs/contracts.md §2.3). name: what a
// screen reader says; label: what is shown.
export const REPLY_LANGUAGES = [
  { id: 'any', label: 'Auto', name: 'Any language' },
  { id: 'en', label: 'EN', name: 'English' },
  { id: 'hi', label: 'हिं', name: 'Hindi', devanagari: true },
];

// The big status word, its hint and the lamp, per view (studioState.js).
// {cut} in a hint is replaced by the cut's timecode.
export const VIEWS = {
  standby: { word: 'Ready', hint: 'Press Talk to go on air · Hindi, English, Hinglish', lamp: 'Standby', tape: 'Standby' },
  tuning: { word: 'Tuning', hint: 'Connecting to the studio…', lamp: 'Connecting', tape: 'Tuning' },
  offair: { word: 'Off air', hint: 'The studio is not reachable. See the message above.', lamp: 'Off air', tape: 'Off air' },
  ready: { word: 'Ready', hint: 'Just start speaking · Hindi, English, Hinglish', lamp: 'On air', tape: 'Standby' },
  listening: { word: 'Listening', hint: 'Outlined words are still being heard and may change', lamp: 'On air · listening', tape: 'Recording you' },
  thinking: { word: 'Thinking', hint: 'Writing the reply · the first sound is on its way', lamp: 'On air · thinking', tape: 'Thinking' },
  speaking: { word: 'Speaking', hint: 'Talk over Vaani at any time to cut in', lamp: 'On air · Vaani speaking', tape: 'Vaani is speaking' },
  cut: { word: 'Cut', hint: 'You came in at {cut} · playback flushed · rest of the reply cancelled', lamp: null, tape: 'Cut, playback flushed' },
};

// Keyboard hints in the dock, per situation.
export const HINTS = {
  idle: ['Press Talk to go on air', 'Enter on Talk to start'],
  vad: ['Hands-free · just talk to cut in', 'Esc = end'],
  ptt: ['Push-to-talk · hold Space to talk', 'Space = talk · Esc = end'],
};

// The error banner: same wording as the old conversation page.
export const ERRORS = {
  micDenied: 'Microphone Permission Denied',
  dropped: 'Connection Dropped',
  service: 'Service Error',
  tryAgain: 'Try Again',
  reconnect: 'Reconnect',
  dismiss: 'Dismiss',
  dismissLabel: 'Dismiss error notification',
};

export const LIVE = {
  maxChars: 140,         // the live line shows the tail of a long reply
  phoneTurns: 3,         // turns under the tape on a phone
};
