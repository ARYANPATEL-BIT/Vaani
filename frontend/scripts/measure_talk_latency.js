/**
 * measure_talk_latency.js -- mic-stop to first audible sample, measured on
 * the real /talk page in a browser, from OUTSIDE the app (no app code is
 * changed or needed). Written for the Studio redesign's before/after check.
 *
 * WHAT IT MEASURES, per turn (hands-free, default persona):
 *   t0 = the end of the last voiced 20 ms window of a speech clip fed in as
 *        the microphone (RMS above 500/32768).
 *   t1 = the first playback AudioBufferSourceNode.start(when) of the reply,
 *        converted to page time, plus AudioContext.outputLatency.
 *   latency = t1 - t0. It excludes the speaker hardware (headless Chromium
 *   reports outputLatency 0), so it is "first sample due at the output".
 *
 * HOW: Playwright injects a script before the page loads that
 *   - replaces getUserMedia with a fake mic that plays the clip on demand,
 *   - wraps AudioBufferSourceNode.prototype.start to see playback scheduling,
 *   - wraps WebSocket to timestamp every JSON message.
 * Both the old and the Studio page have #connect-btn and #disconnect-btn,
 * so the same script runs before and after.
 *
 * RUN (backend running at ws://localhost:8000, frontend dev server up):
 *   1. Set FIXTURE below to the absolute path of the clip on your machine:
 *      docs/findings/persona-voices/persona_default_en_US-kristin-medium_ls1.0_20261008-150404.wav
 *   2. Set URL to the page (e.g. http://localhost:5173/talk).
 *   3. Run this file with a Playwright "run code" tool, e.g. Claude Code's
 *      Playwright MCP: browser_run_code with filename pointing here. It is
 *      one async function of `page` and returns { n, p50, p95, rows }.
 *   Each turn is one paid LLM call: TURNS = 10 means about 10 calls.
 *
 * Percentiles are nearest-rank (with 10 values, p50 is the 5th smallest
 * and p95 the largest).
 */
async (page) => {
  const TURNS = 10;
  const URL = 'http://localhost:5173/talk';
  const FIXTURE = '/ABSOLUTE/PATH/TO/Vaani/docs/findings/persona-voices/persona_default_en_US-kristin-medium_ls1.0_20261008-150404.wav';

  await page.route('**/__vaani_fixture.wav', (r) => r.fulfill({ path: FIXTURE, contentType: 'audio/wav' }));
  await page.addInitScript(() => {
    const m = (window.__m = { starts: [], msgs: [], t0: null, speakIdx: 0, msgIdx: 0 });
    const origStart = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (when = 0, ...rest) {
      if (!this.context.__fake) {
        m.starts.push({ perf: performance.now(), ctxNow: this.context.currentTime, when,
          dur: this.buffer ? this.buffer.duration : 0, outLat: this.context.outputLatency || 0 });
      }
      return origStart.call(this, when, ...rest);
    };
    const OrigWS = window.WebSocket;
    window.WebSocket = class extends OrigWS {
      constructor(...a) {
        super(...a);
        this.addEventListener('message', (e) => {
          if (typeof e.data !== 'string') return;
          try {
            const j = JSON.parse(e.data);
            m.msgs.push({ perf: performance.now(), type: j.type, state: j.state, code: j.code });
          } catch { /* not JSON */ }
        });
      }
    };
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      ctx.__fake = true;
      await ctx.resume();
      const bytes = await (await fetch('/__vaani_fixture.wav')).arrayBuffer();
      const buf = await ctx.decodeAudioData(bytes);
      const d = buf.getChannelData(0);
      const win = Math.round(buf.sampleRate * 0.02);
      let last = 0;
      for (let i = 0; i < d.length; i += win) {
        let s = 0;
        const end = Math.min(i + win, d.length);
        for (let j = i; j < end; j++) s += d[j] * d[j];
        if (Math.sqrt(s / (end - i)) > 500 / 32768) last = end;
      }
      m.lastVoiceS = last / buf.sampleRate;
      const dest = ctx.createMediaStreamDestination();
      window.__speak = () => {
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.connect(dest);
        const lead = 0.05;
        src.start(ctx.currentTime + lead);
        m.t0 = performance.now() + lead * 1000 + m.lastVoiceS * 1000;
        m.speakIdx = m.starts.length;
        m.msgIdx = m.msgs.length;
      };
      return dest.stream;
    };
  });

  await page.goto(URL);
  await page.waitForTimeout(1500);
  await page.click('#connect-btn');
  await page.waitForFunction(() => window.__m.msgs.some((x) => x.type === 'session.started'), null, { timeout: 20000 });
  await page.waitForTimeout(1500);

  // Quiet = the last turn.state is idle and every scheduled buffer has ended.
  const waitQuiet = () => page.waitForFunction(() => {
    const m = window.__m;
    const st = m.msgs.filter((x) => x.type === 'turn.state');
    const lastState = st.length ? st[st.length - 1].state : 'idle';
    const audioEnd = Math.max(0, ...m.starts.map((s) => s.perf + (s.when - s.ctxNow + s.dur) * 1000));
    return lastState === 'idle' && performance.now() > audioEnd + 800;
  }, null, { timeout: 90000, polling: 200 });

  const rows = [];
  for (let k = 0; k < TURNS; k++) {
    await waitQuiet();
    await page.evaluate(() => window.__speak());
    let ok = true;
    try {
      await page.waitForFunction(() => window.__m.starts.length > window.__m.speakIdx, null, { timeout: 45000, polling: 20 });
    } catch { ok = false; }
    rows.push(await page.evaluate((ok) => {
      const m = window.__m;
      const msgs = m.msgs.slice(m.msgIdx);
      const at = (pred) => { const x = msgs.find(pred); return x ? Math.round(x.perf - m.t0) : null; };
      const s = m.starts[m.speakIdx];
      return {
        audibleMs: ok && s ? Math.round(s.perf + (s.when - s.ctxNow) * 1000 + s.outLat * 1000 - m.t0) : null,
        outLatMs: s ? Math.round(s.outLat * 1000) : null,
        finalMs: at((x) => x.type === 'transcript.final'),
        firstTextMs: at((x) => x.type === 'agent.text'),
        audioStartMs: at((x) => x.type === 'audio.start'),
        errors: msgs.filter((x) => x.type === 'error').map((x) => x.code),
        states: msgs.filter((x) => x.type === 'turn.state').map((x) => x.state).join('>'),
      };
    }, ok));
  }
  await waitQuiet().catch(() => {});
  await page.click('#disconnect-btn').catch(() => {});
  const vals = rows.map((r) => r.audibleMs).filter((v) => v !== null).sort((a, b) => a - b);
  const pct = (p) => (vals.length ? vals[Math.min(vals.length - 1, Math.ceil(p * vals.length) - 1)] : null);
  return { lastVoiceS: await page.evaluate(() => window.__m.lastVoiceS), n: vals.length, p50: pct(0.5), p95: pct(0.95), rows };
}
