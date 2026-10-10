# UTask Web

React 18 + Vite frontend for UTask, rebuilt one vertical slice at a time from the `.stitch-assets` reference HTML. Current slices: auth, My Work (Bàn làm việc), student flow (lớp/nhóm, thông báo, hồ sơ), project workspace, teacher class views (read-only).

Architecture and per-feature status live in the canonical docs: [`docs/web/README.md`](../../docs/web/README.md) and [`docs/web/student-flow.md`](../../docs/web/student-flow.md). This README only covers how to run the app.

## Run locally

Requires Node.js 22, Corepack, and pnpm 10.26.0.

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Set `VITE_ENABLE_MOCKS=true` to use MSW test accounts; otherwise point at a real gateway:

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
| Teacher (SE330 ×2, IT3090) | `teacher@utask.test` |
| Teacher (CS402) | `teacher2@utask.test` |
| Teacher (SE360, 100 sinh viên) | `teacher3@utask.test` |

Teacher accounts open `/teacher`. Which classes each account sees, and the demo
data behind them, are described in [`docs/web/teacher-flow.md`](../../docs/web/teacher-flow.md).

## Mock scenarios

Set `VITE_MOCK_SCENARIO` to any of the 30 scenarios defined in `src/mocks/scenarios.ts` — auth (`default`, `slow-network`, `server-error`), My Work states, student-flow states (no team, join pending, leader/member topic, AI key missing, …) and teacher states (`teacher-empty`, `teacher-partial-error`, `teacher-github-error`).

## Verification

```bash
corepack pnpm lint
corepack pnpm test
corepack pnpm build
```

Browser smoke remains required for responsive layout, focus restoration, mock scenarios, and production mock exclusion.