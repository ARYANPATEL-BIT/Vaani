# Vaani — Frontend

React application for real-time voice conversation in Hindi, English,
and Hinglish. Built with Vite.

## Requirements

- **Node.js 18+**
- **npm** (ships with Node)

## Getting started

```bash
cd frontend

# Install dependencies (first time, or after package.json changes).
npm install

# Start the development server with hot module replacement.
npm run dev
```

The dev server runs at http://localhost:5173 by default.

## Available scripts

| Command           | What it does                              |
|-------------------|-------------------------------------------|
| `npm run dev`     | Start Vite dev server with HMR            |
| `npm run build`   | Production build to `dist/`               |
| `npm run preview` | Serve the production build locally        |
| `npm run lint`    | Run ESLint across all source files        |

## Environment variables

Copy `.env.example` to `.env.local` and adjust as needed:

```bash
cp .env.example .env.local
```

| Variable              | Default                          | Purpose                    |
|-----------------------|----------------------------------|----------------------------|
| `VITE_API_BASE_URL`   | `http://localhost:8000`          | Backend API base URL       |
| `VITE_WS_SESSION_URL` | `ws://localhost:8000/ws/session` | WebSocket session endpoint |

## Project structure

```
src/
├── main.jsx              # Entry point — mounts RouterProvider
├── router.jsx            # All application routes
├── config.js             # Centralised configuration
├── index.css             # Global styles and CSS variables
├── components/
│   └── AppLayout.jsx     # Persistent page shell (header + Outlet)
└── pages/
    ├── ConversationPage.jsx   # Main voice conversation UI
    └── NotFoundPage.jsx       # 404 catch-all
```

## Routing

Routes are defined in `src/router.jsx` using react-router-dom v7.

| Path | Page               | Status   |
|------|--------------------|----------|
| `/`  | ConversationPage   | Active   |
| `*`  | NotFoundPage       | Active   |

Future routes (enrolment, profiles, settings) are commented in the
router and will be added as lazy-loaded imports.
Placeholder. The React frontend is owned by Samyak and lives here.

Nothing in this directory is built yet. See the repository root `README.md`
for how to run the backend, and `docs/` for the project specification.
