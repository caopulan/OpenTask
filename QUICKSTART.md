# Quick Start

[中文版本](QUICKSTART.ZH.md) | [Project Overview](README.md)

This guide shows the intended OpenClaw-native path first, then the optional OpenTask backend and UI.

## What You Will Have

By the end you will have:

- a validated workflow under `workflows/`
- a run folder under `runs/<runId>/`
- a root-session-bound workflow that can continue through OpenClaw cron
- an optional control plane at `http://127.0.0.1:8000` and `http://127.0.0.1:5174/`

## 1. Install the Skill into OpenClaw

Copy or symlink [skills/opentask](skills/opentask) into the shared skills directory configured by your OpenClaw deployment, using the installed name `opentask`.

Before continuing, confirm the agent can read [skills/opentask/SKILL.md](skills/opentask/SKILL.md) through that installed skill.

## 2. Install Dependencies

```bash
uv sync --dev
pnpm --dir web install
```

## 3. Set the Registry Root

Choose the registry root that OpenTask should manage:

```bash
export OPENTASK_REGISTRY_ROOT=/path/to/opentask-registry
export OPENTASK_GATEWAY_URL=ws://127.0.0.1:18789
```

For a first local setup, using this repository root is acceptable.

## 4. Validate the Sample Workflow

```bash
uv run opentask workflow validate workflows/research-demo.task.md
```

## 5. Start the Workflow from OpenClaw

In the OpenClaw conversation where you want the long-running task to live:

1. Use the OpenTask skill at [skills/opentask/SKILL.md](skills/opentask/SKILL.md).
2. Ask the agent to treat the current conversation as the root orchestrator session.
3. Ask it to create or validate the workflow under `workflows/`.
4. Ask it to bind a run to the current session and start execution.

Example prompt:

```text
Use the opentask skill for this conversation. Treat this session as the root orchestrator, create or validate the workflow, bind a run to this session, and keep it running until completion.
```

Under the hood, the skill should resolve the current `sessionKey`, `agentId`, and `deliveryContext`, then create the run and start cron. The CLI exists for operators and tests, not as the primary user-facing path.

## 6. Inspect the Registry

Open the run folder:

```bash
ls runs/<runId>
```

You should see:

- `workflow.lock.md`
- `state.json`
- `refs.json`
- `events.jsonl`
- `control.jsonl`
- `nodes/`

The contract for each file is documented in [docs/registry-spec.md](docs/registry-spec.md).

## 7. Control the Workflow from OpenClaw

Continue controlling the run from the same OpenClaw conversation. Typical examples:

- Pause:
  `Pause this workflow after the current active node finishes.`
- Resume:
  `Resume the workflow and continue from the current plan.`
- Request an update:
  `Send me a short milestone update in this conversation.`
- Change cadence:
  `Slow the cron cadence because this can run in the background.`

The skill should translate those requests into native OpenClaw actions:

- append or interpret control intent through `control.jsonl`
- update workflow or run files when needed
- patch cron through OpenClaw tools
- send explicit user-visible messages only when appropriate

## 8. Operator Equivalents

These commands are for operators, debugging, UI integrations, and tests. They are not the primary control path for end users:

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
uv run opentask control send_message <runId> --message "Still running."
uv run opentask control patch_cron <runId> --patch-json '{"enabled": true}'
```

## 9. Start the Optional Backend

```bash
uv run opentask-api
```

The backend indexes the registry and exposes control APIs at `http://127.0.0.1:8000`.

Useful endpoints:

- `GET /api/runs`
- `GET /api/runs/<runId>`
- `GET /api/runs/<runId>/events`
- `POST /api/runs/<runId>/actions/send_message`

## 10. Start the Optional Web UI

```bash
pnpm --dir web dev
```

Open [http://127.0.0.1:5174/](http://127.0.0.1:5174/).

The UI is for:

- browsing runs
- viewing DAG structure
- inspecting node artifacts and session bindings
- issuing explicit control actions

It is not the preferred production surface for starting new tasks.

## 11. Debug Path: Create a Run Through the API

For local debugging or testing, you can still create a run through the backend:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "title": "Debug run",
    "taskText": "Inspect README.md and write a short report."
  }'
```

This uses the same core library, but it is an operator convenience path rather than the preferred OpenClaw-native entry.
