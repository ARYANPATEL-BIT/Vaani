/* global process */
/**
 * measure_proxy_latency.js -- what the Vite dev-server proxy adds to
 * /ws/session (feat/frontend-auth). Results: docs/findings/frontend-auth/.
 *
 * RUN (backend on 127.0.0.1:8000 with [auth] enabled=false, `npm run dev`):
 *   node frontend/scripts/measure_proxy_latency.js 100
 * No turn is spoken and no audio is sent, so no paid call is made.
 *
 * Per run: handshake = new WebSocket -> open; roundtrip = send session.start
 * -> receive session.started. Direct and proxied runs alternate, so drift on
 * the machine hits both equally.
 */
const N = Number(process.argv[2] || 50);
const WARMUP = 3;
const TARGETS = { direct: 'ws://127.0.0.1:8000/ws/session', proxy: 'ws://localhost:5173/ws/session' };
const START = JSON.stringify({ type: 'session.start', persona: 'default', mode: 'vad', reply_language: 'any',
  audio: { sample_rate: 16000, channels: 1, frame_ms: 20 } });

function once(url) {
  return new Promise((resolve, reject) => {
    const t0 = performance.now();
    let t1 = 0;
    const ws = new WebSocket(url);
    const timer = setTimeout(() => { ws.close(); reject(new Error('timeout ' + url)); }, 10000);
    ws.onopen = () => { t1 = performance.now(); ws.send(START); };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      const msg = JSON.parse(ev.data);
      if (msg.type === 'session.started') {
        const t2 = performance.now();
        clearTimeout(timer);
        ws.close();
        resolve({ handshake: t1 - t0, roundtrip: t2 - t1 });
      } else if (msg.type === 'error') {
        clearTimeout(timer); ws.close(); reject(new Error(msg.code));
      }
    };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('ws error ' + url)); };
  });
}

const pct = (xs, p) => { const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.ceil(p / 100 * s.length) - 1)]; };
const rows = { direct: [], proxy: [] };
for (let i = 0; i < WARMUP + N; i += 1) {
  for (const name of ['direct', 'proxy']) {
    const r = await once(TARGETS[name]);
    if (i >= WARMUP) rows[name].push(r);
    await new Promise((res) => setTimeout(res, 50));
  }
}
console.log(`n=${N} per target (nearest-rank percentiles, ms)`);
for (const metric of ['handshake', 'roundtrip']) {
  for (const name of ['direct', 'proxy']) {
    const xs = rows[name].map((r) => r[metric]);
    console.log(`${metric.padEnd(9)} ${name.padEnd(6)} p50 ${pct(xs, 50).toFixed(2).padStart(7)}  p95 ${pct(xs, 95).toFixed(2).padStart(7)}`);
  }
}
