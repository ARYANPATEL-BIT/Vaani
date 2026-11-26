/* global process */
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
//
// ONE ORIGIN. The browser loads the page from this server (:5173) and also
// sends its backend calls here; the proxy below forwards them to the FastAPI
// backend. To the browser everything is one origin, so the vaani_session
// cookie (SameSite=Lax, httpOnly) goes along with every /auth call and the
// /ws/session upgrade, locally and through a Cloudflare tunnel alike.
export default defineConfig(({ mode }) => {
  // '' as the prefix: read every name in frontend/.env*, not only VITE_ ones.
  // VAANI_PROXY_TARGET has no VITE_ prefix on purpose: only this server reads
  // it; Vite never puts it into the code it sends to the browser.
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VAANI_PROXY_TARGET || 'http://127.0.0.1:8000'
  // The voice studio is its own process (studio/, port 8100 in
  // studio/config.toml). Same idea: the browser only ever talks to :5173.
  const studioTarget = env.VAANI_STUDIO_PROXY_TARGET || 'http://127.0.0.1:8100'

  // changeOrigin is left false (the default): the backend gets the browser's
  // own Host and Origin headers. Origin matters: auth.py checks it against
  // [auth] allowed_origins on sign-in, logout and the WebSocket handshake.
  const proxy = {
    '/auth': { target },
    '/health': { target },
    '/ws': { target, ws: true }, // ws: also forward WebSocket upgrades
    // Voice studio routes (docs/contracts.md section 4). changeOrigin stays
    // false here too: the studio checks Origin the way auth.py does.
    '/studio': { target: studioTarget },
  }

  // Vite refuses requests whose Host it does not know (a guard against DNS
  // rebinding). A quick Cloudflare tunnel gets a new random
  // <name>.trycloudflare.com each run; the leading dot allows any of them.
  const allowedHosts = ['.trycloudflare.com', '.ngrok-free.app', '.ngrok-free.dev']

  return {
    plugins: [react()],
    server: { proxy, allowedHosts },
    // The same for `npm run preview` (the built app), so it works the same way.
    preview: { proxy, allowedHosts },
  }
})
