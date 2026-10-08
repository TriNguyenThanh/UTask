# UTask Web

React 18 + Vite frontend for UTask. Current slice: auth only — mock login, forgot-password and reset-password flows rebuilt one screen at a time from the `.stitch-assets` reference HTML.

## Run locally

Requires Node.js 22, Corepack, and pnpm 10.26.0.

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Development mode enables MSW by default, so test accounts work without creating `.env.local`. To connect a real backend instead:

```env
VITE_ENABLE_MOCKS=false
VITE_API_BASE_URL=http://localhost:<gateway-port>
```

Production builds never register MSW. `VITE_API_BASE_URL` defaults to empty so browser requests stay on same-origin `/api/...` gateway paths.

## Development accounts

All accounts use password `demo1234`.

| Role | Email |
|---|---|
| Leader | `leader@utask.test` |
| Member | `member@utask.test` |
| Student (no group) | `student@utask.test` |

## Mock scenarios

Set `VITE_MOCK_SCENARIO` to one of:

- `default`
- `slow-network` (all handlers delayed 1200 ms)
- `server-error` (auth endpoints return 500)

## Current scope

- `/login`, `/forgot-password`, `/reset-password` with shared academic auth shell (`.stitch-assets/html/01..03`).
- Login/refresh session flow; protected-route returnTo restore.
- Workspace shell placeholder (`/`): navigation shell for future screens; only logout active.

Project, task, classroom, notification and settings screens were intentionally removed; rebuild vertical slice by slice following `docs/frontend/UTask_Leader_Member_UX_Flow.md` and the Stitch HTML under `.stitch-assets/html`.

## Verification

```bash
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm build
```

Browser smoke remains required for responsive layout, focus restoration, mock scenarios, and production mock exclusion.