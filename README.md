# OpenTask

<p align="center">
  <img src="web/src/assets/hero.png" alt="OpenTask" width="220">
</p>

<p align="center">File-backed workflow orchestration for long-running OpenClaw sessions.</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#workflow-format">Workflow Format</a> •
  <a href="#api">API</a> •
  <a href="#current-limitations">Current Limitations</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI backend">
  <img src="https://img.shields.io/badge/runtime-OpenClaw-111111" alt="OpenClaw runtime">
  <img src="https://img.shields.io/badge/status-experimental-orange" alt="Experimental status">
</p>

OpenTask is a web application and runtime for planning, executing, and auditing agent workflows on top of OpenClaw. It keeps the workflow DAG, run state projection, and append-only event log on disk, while OpenClaw handles execution facts such as sessions, child sessions, and cron-driven turns.

It is built for developers and operators who need inspectable, long-running agent workflows instead of one-shot prompts. You can start from a plain task description or a versioned Markdown workflow, watch the graph evolve in a web UI, and keep driving the run until every node reaches a terminal state.

## Features ✨

- Markdown-first workflows with YAML frontmatter
- File-backed runtime store under `.opentask/runs/<runId>/`
- Real OpenClaw integration for planner, driver, node, and subagent sessions
- Live graph mutation through driver directives
- Web UI for run list, DAG view, timeline, and node controls
- Cross-process run coordination to prevent duplicate dispatch
- Recoverable state with `workflow.lock.md`, `state.json`, `events.jsonl`, and `openclaw.json`

## How It Works ⚙️

OpenTask and OpenClaw split responsibilities cleanly:

| Layer | Owned by OpenTask | Owned by OpenClaw |
| --- | --- | --- |
| Workflow model | DAG definition, workflow lock, node dependencies | None |
| Runtime state | `state.json`, `events.jsonl`, node artifacts | None |
| Execution | Dispatch policy, driver directive application, operator actions | Sessions, child sessions, cron jobs, run completion |
| UI | Run list, graph, timeline, controls | None |

That split lets you keep a human-readable audit trail on disk without giving up OpenClaw's session and cron machinery.

## Installation

### Prerequisites

- Python 3.12+
- `uv`
- Node.js and `pnpm`
- A running OpenClaw Gateway
- An OpenClaw agent workspace for this repository

### Backend and frontend dependencies

```bash
uv sync --dev
pnpm --dir web install
```

### OpenClaw workspace setup

By default OpenTask targets the OpenClaw agent `opentask`. Point that agent's workspace at this repository, or override it with `OPENTASK_AGENT_ID`.

OpenTask automatically reuses local device auth material from:

- `~/.openclaw/identity/device.json`
- `~/.openclaw/identity/device-auth.json`

Override them only if needed:

```bash
export OPENTASK_GATEWAY_URL=ws://127.0.0.1:18789
export OPENTASK_AGENT_ID=opentask
export OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH=/path/to/device.json
export OPENTASK_GATEWAY_DEVICE_AUTH_PATH=/path/to/device-auth.json
```

## Quick Start

### 1. Start the backend

```bash
uv run opentask-api
```

The API listens on `http://127.0.0.1:8000`.

### 2. Start the web UI

```bash
pnpm --dir web dev
```

The Vite app listens on `http://127.0.0.1:5174/` and proxies `/api` plus WebSocket traffic to the backend.

### 3. Create a run from free-form task text

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "title": "First run",
    "taskText": "Review AGENTS.md and write a short report about repo conventions."
  }'
```

Example response:

```json
{
  "runId": "opentask-1234abcd",
  "status": "running",
  "workflowId": "first-run"
}
```

### 4. Inspect runs and events

```bash
curl http://127.0.0.1:8000/api/runs
curl http://127.0.0.1:8000/api/runs/opentask-1234abcd/events
```

### 5. Launch a run from a workflow file

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "workflowPath": "workflows/research-demo.task.md"
  }'
```

## Workflow Format

Versioned workflows live in `workflows/*.task.md` and use Markdown plus YAML frontmatter.

Minimal example:

```md
---
workflowId: quick-demo
title: Quick demo
defaults:
  agentId: opentask
nodes:
  - id: execute-task
    title: Execute task
    kind: session_turn
    needs: []
    prompt: Write a short report.
    outputs:
      mode: report
      requiredFiles:
        - nodes/execute-task/report.md
  - id: summary
    title: Summary
    kind: summary
    needs:
      - execute-task
    prompt: Summarize the run.
    outputs:
      mode: report
      requiredFiles:
        - nodes/summary/report.md
---
```

Supported node kinds:

- `session_turn`
- `subagent`
- `wait`
- `approval`
- `summary`

Supported output modes:

- `notify`
- `report`

Driver sessions can also emit structured mutation blocks to add or rewire nodes while a run is active.

See the full sample in [workflows/research-demo.task.md](workflows/research-demo.task.md).

## Runtime Layout 🗂️

Each run lives under `.opentask/runs/<runId>/`:

| Path | Purpose |
| --- | --- |
| `workflow.lock.md` | Frozen workflow snapshot for this run |
| `state.json` | Current state projection used by the API and UI |
| `events.jsonl` | Append-only audit trail |
| `openclaw.json` | Planner, driver, cron, and node session references |
| `driver.context.md` | Latest driver review prompt snapshot |
| `nodes/<nodeId>/` | Reports and node-specific artifacts |
| `.run.lock` | Cross-process coordination lock for that run |

The runtime store is intentionally git-ignored.

## API

Available endpoints:

- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/events`
- `POST /api/runs/{runId}/actions/{pause|resume|retry|skip|approve|tick}`
- `WS /api/runs/{runId}/stream`

Example operator action:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/tick \
  -H 'content-type: application/json' \
  -d '{}'
```

## Configuration 🔧

Common environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENTASK_GATEWAY_URL` | `ws://127.0.0.1:18789` | OpenClaw Gateway URL |
| `OPENTASK_AGENT_ID` | `opentask` | Agent/workspace that owns run sessions |
| `OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH` | `~/.openclaw/identity/device.json` | Device identity file |
| `OPENTASK_GATEWAY_DEVICE_AUTH_PATH` | `~/.openclaw/identity/device-auth.json` | Device auth token store |

## Documentation 📚

Start with these repository entry points:

- [README.md](README.md) for setup and operating model
- [workflows/research-demo.task.md](workflows/research-demo.task.md) for a complete workflow example
- [web/README.md](web/README.md) for frontend-specific notes
- [tests/test_service.py](tests/test_service.py) for orchestration behavior and regression coverage

## Current Limitations

OpenTask is usable, but it is not finished productized infrastructure yet.

- It expects a running OpenClaw Gateway and a configured local agent workspace.
- The runtime store is local filesystem based, not distributed storage.
- There is no visual DAG editor yet; the UI is inspect-and-control only.
- The project does not currently ship a packaged release or installer.

## Contributing 🤝

Issues and pull requests are welcome. For larger changes, open an issue first so the workflow and storage model stay coherent.

Current development flow:

```bash
uv sync --dev
pnpm --dir web install
uv run pytest
pnpm --dir web lint
pnpm --dir web build
```

This repository also expects Conventional Commits and uses `uv` for Python environment and dependency management.

## License 📄

This repository does not currently include an open source license file. Until a license is added, treat the code as all rights reserved.
