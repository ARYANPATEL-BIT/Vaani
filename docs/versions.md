# Pinned versions

The learning documents cite this file for the exact version of every library
and tool in use. These are the versions resolved into `backend/uv.lock` on
2026-09-22. Regenerate this list after any `uv lock`.

## Toolchain

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11 | Minimum `>=3.11`; local interpreter 3.11.9 |
| uv | 0.11.28 | Package manager; pinned identically in CI |
| Node.js | 18+ | Minimum `>=18`; local runtime v25.8.1 |
| npm | 10+ | Package manager; local version 11.11.0 |

## Backend runtime dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| fastapi | 0.141.1 | MIT | Web framework: routing, validation, ASGI app |
| uvicorn | 0.53.0 | BSD-3-Clause | ASGI server that runs the app |
| pydantic-settings | 2.15.0 | MIT | Typed settings from TOML + environment |

## Frontend runtime dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| react | 19.2.8 | MIT | Core UI library for declarative views |
| react-dom | 19.2.8 | MIT | DOM renderer for React |
| react-router-dom | 7.18.4 | MIT | Declarative client-side routing |

## Backend dev/test dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| pytest | 9.1.1 | MIT | Test runner |
| httpx | 0.28.1 | BSD-3-Clause | HTTP client; powers FastAPI's TestClient |
| ruff | 0.16.8 | MIT | Linter and formatter |

## Frontend dev dependencies (direct)

| Package | Version | License | Why it is here |
|---|---|---|---|
| vite | 8.3.0 | MIT | Frontend build tool and dev server |
| @vitejs/plugin-react | 6.1.1 | MIT | React Fast Refresh and JSX support |
| eslint | 10.10.0 | MIT | JavaScript linter |
| globals | 17.12.0 | MIT | Global identifier definitions for ESLint |
| eslint-plugin-react-hooks | 7.1.1 | MIT | Enforces Rules of Hooks |
| eslint-plugin-react-refresh | 0.5.6 | MIT | Validates components for Fast Refresh |

## Key transitive dependencies (pulled in automatically)

| Package | Version | Pulled in by |
|---|---|---|
| pydantic | 2.13.5 | fastapi, pydantic-settings |
| pydantic-core | 2.46.5 | pydantic |
| starlette | 1.6.0 | fastapi |
| anyio | 4.15.1 | starlette, httpx |
| python-dotenv | 1.2.3 | pydantic-settings |

Licenses above are the well-known licenses for these projects; none is
copyleft, so none constrains how Vaani is distributed. Verify against each
package's own metadata if a license question becomes important.
