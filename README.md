# OpenTask

OpenTask is a file-backed workflow orchestrator for OpenClaw. It keeps the workflow DAG, run state, and audit trail on disk, drives execution through OpenClaw sessions and cron, and exposes a web UI for graph inspection and operator controls.

## Stack

- Backend: FastAPI, Pydantic v2, watchfiles, websockets
- Runtime store: Markdown workflow lock + JSON state + JSONL events under `.opentask/runs/`
- Frontend: React, Vite, TanStack Query, React Flow

## Quickstart

```bash
uv sync --dev
pnpm install --dir web
uv run opentask-api
pnpm --dir web dev
```

The backend listens on `http://127.0.0.1:8000`. The Vite dev server proxies `/api` and websocket traffic there by default. If you host the frontend separately, set `VITE_API_BASE` to the backend origin.

For local OpenClaw usage, OpenTask will automatically reuse `~/.openclaw/identity/device.json` and `~/.openclaw/identity/device-auth.json` unless you override them with `OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH` and `OPENTASK_GATEWAY_DEVICE_AUTH_PATH`.

## Runtime Layout

Each run lives under `.opentask/runs/<runId>/`:

- `workflow.lock.md`: frozen workflow snapshot
- `state.json`: current run projection
- `events.jsonl`: append-only audit trail
- `openclaw.json`: planner, driver, cron, and node session references
- `driver.context.md`: latest autonomous driver review prompt
- `nodes/<nodeId>/`: per-node artifacts and reports

The runtime store and local planning/reference notes are intentionally ignored by git.

## Workflow Format

Versioned workflows live in `workflows/*.task.md` and use `Markdown + YAML frontmatter`.

Each node supports:

- `id`
- `title`
- `kind`: `session_turn`, `subagent`, `wait`, `approval`, `summary`
- `needs`
- `prompt`
- `outputs.mode`: `notify` or `report`

Driver settings support:

- `driver.cron`
- `driver.timeoutMs`
- `driver.wakeMode`

See [workflows/research-demo.task.md](/Users/chunqiu/Documents/workspace/OpenTask/workflows/research-demo.task.md) for a complete sample.

## API Surface

- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/events`
- `POST /api/runs/{runId}/actions/{pause|resume|retry|skip|approve|tick}`
- `WS /api/runs/{runId}/stream`

## Current OpenClaw Integration

- A run bootstraps one planner session, one driver session, and one driver cron.
- `session_turn` nodes use persistent per-node sessions.
- `subagent` nodes use `sessions_spawn` and record `childSessionKey` in run state.
- Driver sessions can emit `<opentask-mutation>{...}</opentask-mutation>` blocks to add or rewire nodes while a run is active.
- The backend automatically sends driver review turns when run state changes and tracks the active driver run in `openclaw.json`.
- Wait and approval nodes are resolved from local run state plus operator actions.

## Verification

```bash
uv run pytest
pnpm --dir web lint
pnpm --dir web build
```
