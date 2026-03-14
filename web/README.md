# OpenTask Web

The frontend is a React Flow based control room for OpenTask runs. It shows the run list, DAG, event timeline, and operator actions for pause, resume, retry, skip, approve, and force tick.

## Commands

```bash
pnpm install
pnpm dev
pnpm lint
pnpm build
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`. For a separately hosted frontend, set `VITE_API_BASE` before running or building.
