# Quick Start

[中文版本](QUICKSTART.ZH.md) | [Project Overview](README.md)

This tutorial gets a real OpenTask run onto your screen and onto disk. If your local OpenClaw Gateway is already available, the full walkthrough usually takes less than 10 minutes.

## What You Will Get

By the end of this tutorial you will have:

- the backend running on `http://127.0.0.1:8000`
- the web UI running on `http://127.0.0.1:5174/`
- at least one run created from free-form task text
- at least one run created from the sample workflow
- a local runtime archive under `.opentask/runs/<runId>/`

## 1. Prerequisites

Make sure these are ready before you start:

- Python `3.12+`
- `uv`
- Node.js and `pnpm`
- a running OpenClaw Gateway
- an OpenClaw agent named `opentask` whose workspace points at this repository

If your Gateway limits tool access, allow `sessions_spawn` for the `opentask` agent. Subagent nodes depend on it.

## 2. Install Dependencies

```bash
uv sync --dev
pnpm --dir web install
```

## 3. Confirm OpenClaw Connectivity

OpenTask reuses local OpenClaw device-auth files by default:

- `~/.openclaw/identity/device.json`
- `~/.openclaw/identity/device-auth.json`

If you need custom settings, export them before starting the backend:

```bash
export OPENTASK_GATEWAY_URL=ws://127.0.0.1:18789
export OPENTASK_AGENT_ID=opentask
export OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH=/path/to/device.json
export OPENTASK_GATEWAY_DEVICE_AUTH_PATH=/path/to/device-auth.json
```

## 4. Start the Backend

```bash
uv run opentask-api
```

Leave this terminal running. The API should now answer:

```bash
curl http://127.0.0.1:8000/api/runs
```

## 5. Start the Web UI

In a second terminal:

```bash
pnpm --dir web dev
```

Open [http://127.0.0.1:5174/](http://127.0.0.1:5174/). The Vite dev server proxies both `/api` and the run stream WebSocket to the backend.

## 6. Create Your First Run from Task Text

Use the API directly:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "title": "Quickstart free-form run",
    "taskText": "Inspect README.md and write a short report about what OpenTask does."
  }'
```

Example response:

```json
{
  "runId": "opentask-1234abcd",
  "workflowId": "quickstart-free-form-run",
  "status": "running"
}
```

Copy the returned `runId`. You can now:

- refresh the UI and open the run from the list
- inspect the event log with `GET /api/runs/<runId>/events`
- force a scheduling cycle with the `tick` action

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/tick \
  -H 'content-type: application/json' \
  -d '{}'
```

## 7. Create a Run from the Sample Workflow

OpenTask ships with a runnable workflow example:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "workflowPath": "workflows/research-demo.task.md"
  }'
```

That workflow demonstrates:

- a `session_turn` node for the primary execution
- a `subagent` node using `sessions_spawn`
- an `approval` gate that waits for an operator action
- a terminal `summary` node

## 8. Inspect and Control the Run

List runs:

```bash
curl http://127.0.0.1:8000/api/runs
```

Read one run:

```bash
curl http://127.0.0.1:8000/api/runs/opentask-1234abcd
```

Read the event timeline:

```bash
curl http://127.0.0.1:8000/api/runs/opentask-1234abcd/events
```

Pause a run:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/pause \
  -H 'content-type: application/json' \
  -d '{}'
```

Resume a run:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/resume \
  -H 'content-type: application/json' \
  -d '{}'
```

Approve the sample workflow gate:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/approve \
  -H 'content-type: application/json' \
  -d '{
    "nodeId": "approval-gate"
  }'
```

Retry a node:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/retry \
  -H 'content-type: application/json' \
  -d '{
    "nodeId": "gather-context"
  }'
```

Everything above is also available in the web UI through the run list, graph view, event timeline, and node detail panel.

## 9. Inspect the Runtime Archive

Each run is written to `.opentask/runs/<runId>/`.

Key files:

- `workflow.lock.md` keeps the frozen workflow snapshot
- `state.json` is the current API/UI state projection
- `events.jsonl` is the append-only audit trail
- `openclaw.json` stores planner, driver, cron, and node session references
- `nodes/<nodeId>/` stores reports and node-level artifacts
- `.run.lock` prevents duplicate cross-process mutations on the same run

This means you can inspect a run without querying the UI, and you can keep the runtime store out of git.

## 10. Troubleshooting

### `gateway error: device identity required`

Your OpenClaw device-auth files are missing or not readable. Check:

- `~/.openclaw/identity/device.json`
- `~/.openclaw/identity/device-auth.json`

Or point OpenTask at alternate files with `OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH` and `OPENTASK_GATEWAY_DEVICE_AUTH_PATH`.

### New runs stay in `running`, but nodes do not advance

Check all three layers:

- the backend terminal for Gateway or parsing errors
- the UI timeline for `driver.requested`, `node.started`, and `node.completed`
- `.opentask/runs/<runId>/events.jsonl` for the authoritative audit trail

### `subagent` nodes fail immediately

Your OpenClaw Gateway likely does not allow `sessions_spawn` for the `opentask` agent yet.

### The UI loads, but API calls fail

Make sure `uv run opentask-api` is running on `127.0.0.1:8000`. The frontend dev server depends on that proxy target by default.

## Next Steps

- Read [README.md](README.md) for the architecture and operating model.
- Read [workflows/research-demo.task.md](workflows/research-demo.task.md) to understand the workflow schema.
- Read [web/README.md](web/README.md) for frontend-specific commands.
