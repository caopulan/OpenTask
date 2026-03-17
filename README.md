# OpenTask

<p align="center">
  <img src="web/src/assets/hero.png" alt="OpenTask" width="220">
</p>

<p align="center">OpenClaw-native workflow registry, control plane, and visualization layer.</p>

<p align="center">
  English ·
  <a href="README.ZH.md">中文</a> ·
  <a href="QUICKSTART.md">Quick Start</a> ·
  <a href="docs/registry-spec.md">Registry Spec</a>
</p>

OpenTask is built around a simple split:

- OpenClaw executes the work.
- OpenTask keeps the workflow registry, run state projection, audit trail, and control UI.

The workflow must keep running even when the OpenTask backend or frontend is down. The shared source of truth is a registry directory containing versioned workflows and run folders under `runs/`.

For real runs, that registry root should be the stable OpenClaw workspace or the configured `OPENTASK_REGISTRY_ROOT`, not a throwaway temp directory.

## What It Ships

- A registry contract for workflows, runs, refs, events, controls, node-local working memory, and node outputs
- A Python core library and `opentask` CLI for deterministic state changes
- A shared OpenClaw skill at [skills/opentask/SKILL.md](skills/opentask/SKILL.md)
- A FastAPI backend that indexes the registry and exposes control APIs
- A React control plane for DAG visualization and explicit operator actions

## Architecture

### Execution Plane

OpenClaw remains the execution plane.

- The current Discord or channel session becomes the root orchestrator session.
- Subtasks are delegated through `sessions_spawn`.
- Cron keeps waking the root session until the workflow reaches a terminal state.
- Internal orchestration messages run without delivery.
- User-visible updates go out as explicit progress messages.

### Control Plane

OpenTask becomes read-mostly control plane.

- The backend indexes the registry and exposes REST plus WebSocket endpoints.
- The web UI renders runs, DAGs, timeline events, node artifacts, and session bindings.
- Operator actions are written as explicit controls, not ad hoc in-memory mutations.

## Registry Layout

See the formal spec in [docs/registry-spec.md](docs/registry-spec.md).

```text
<registry-root>/
  workflows/
    *.task.md
  runs/
    <runId>/
      workflow.lock.md
      state.json
      refs.json
      events.jsonl
      control.jsonl
      nodes/
        <nodeId>/
          plan.md
          findings.md
          progress.md
          handoff.md
          report.md
          result.json
```

Key files:

- `state.json`: UI projection
- `refs.json`: OpenClaw runtime bindings such as source session, root session, cron, child sessions
- `events.jsonl`: append-only audit trail
- `control.jsonl`: explicit operator or UI control requests
- `nodes/<nodeId>/plan.md`, `findings.md`, `progress.md`: canonical node-local working memory
- `nodes/<nodeId>/handoff.md`: canonical parent-to-child brief for subagent nodes

## Installation

Prerequisites:

- Python 3.12+
- `uv`
- Node.js and `pnpm`
- A running OpenClaw Gateway
- An OpenClaw deployment with a shared skills directory

Install dependencies:

```bash
uv sync --dev
pnpm --dir web install
```

Common environment variables:

```bash
export OPENTASK_REGISTRY_ROOT=$PWD
export OPENTASK_GATEWAY_URL=ws://127.0.0.1:18789
export OPENTASK_AGENT_ID=opentask
```

OpenTask automatically reuses local OpenClaw device auth from `~/.openclaw/identity/`.

### Install into OpenClaw

Install the OpenTask skill into the shared skills directory used by your OpenClaw deployment:

1. Clone this repository and install dependencies.
2. Copy or symlink [skills/opentask](skills/opentask) into the OpenClaw shared skills directory as `opentask`.
3. Set `OPENTASK_REGISTRY_ROOT` to the stable registry root you want OpenTask to manage, or ensure the OpenClaw agent workspace itself is the intended registry root.
4. In the target OpenClaw conversation, use the installed `opentask` skill.

If the agent cannot read [skills/opentask/SKILL.md](skills/opentask/SKILL.md), it is not installed correctly for OpenClaw yet.

## Preferred Workflow

The primary path is OpenClaw-native:

1. The user asks for a long-running task in the current Discord or channel conversation.
2. The OpenClaw agent uses [skills/opentask/SKILL.md](skills/opentask/SKILL.md).
3. The agent resolves the current `sessionKey`, `deliveryContext`, and registry root.
4. The agent creates or validates a reusable workflow file under `workflows/`. That source workflow should stay reusable and must not contain run-local metadata like concrete registry paths, `runId`, or transient status notes.
5. The agent creates or binds a run for that session using the registry protocol, finishes scaffolding canonical node memory and lifecycle records, and only then begins execution. It may optionally use the `opentask` CLI or core library when deterministic helper commands are useful.
6. OpenClaw cron and subagents continue execution from there.

Manual equivalent:

```bash
uv run opentask run create \
  --workflow-path workflows/research-demo.task.md \
  --source-session-key 'agent:main:discord:channel:1234567890' \
  --source-agent-id main \
  --delivery-context-json '{"channel":"discord","to":"channel:1234567890"}'
```

## Debug and Operator Surfaces

### CLI

Validate a workflow:

```bash
uv run opentask workflow validate workflows/research-demo.task.md
```

Pause or resume:

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
```

Send an explicit progress update:

```bash
uv run opentask control send_message <runId> --message "Still running."
```

Patch cron:

```bash
uv run opentask control patch_cron <runId> --patch-json '{"enabled": true}'
```

### Backend

Start the backend:

```bash
uv run opentask-api
```

The API listens on `http://127.0.0.1:8000`.

### Web UI

Start the frontend:

```bash
pnpm --dir web dev
```

The Vite app listens on `http://127.0.0.1:5174/`.

The UI is a control plane, not the primary task-start surface. It is best used for:

- viewing the registry-backed run list
- inspecting DAG structure and node artifacts
- reviewing audit events
- issuing explicit actions such as `pause`, `resume`, `retry`, `skip`, `approve`, `send_message`, and `patch_cron`

## API

Public endpoints:

- `GET /api/runs`
- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/events`
- `POST /api/runs/{runId}/actions/{pause|resume|retry|skip|approve|send_message|patch_cron|tick}`
- `WS /api/runs/{runId}/stream`

`POST /api/runs` still exists, but it is now a debug and operator wrapper around the same core library. It is not the preferred production entry point.

## Documentation

- [QUICKSTART.md](QUICKSTART.md)
- [docs/registry-spec.md](docs/registry-spec.md)
- [skills/opentask/SKILL.md](skills/opentask/SKILL.md)
- [workflows/research-demo.task.md](workflows/research-demo.task.md)
- [web/README.md](web/README.md)

## Current Limitations

- The preferred start path assumes the OpenClaw agent can resolve the current session, delivery context, and registry root before it starts writing run files.
- Registry locking is local filesystem locking, not distributed locking.
- The frontend is intentionally read-mostly and does not offer free-form DAG editing.
- This repository still ships API debug entrypoints because they are useful for operators and tests.
