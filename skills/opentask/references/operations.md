# Native Operations

[中文版本](./operations.ZH.md)

Use native OpenClaw tools and file edits. Do not assume the OpenTask backend or CLI is available.

## 1. Filesystem Work

Use normal file tools to:

- create `workflows/*.task.md`
- create `runs/<runId>/...`
- update `workflow.lock.md`, `state.json`, `refs.json`
- append lines to `events.jsonl`
- write `nodes/<nodeId>/report.md` and `result.json`

When `control.jsonl` must exist before any actions are appended, create it as an empty file. Do not write placeholder comments or prose into that file.

## 2. Session Discovery

Use `sessions_list` to resolve the current session entry and capture:

- `sessionKey`
- `agentId`
- `deliveryContext`

## 3. Subagent Creation

Use `sessions_spawn` when a node is delegated.

The child prompt should include:

- run path
- node id
- scoped task
- dependency artifacts to read
- required outputs to write
- a rule to avoid global state mutation
- a rule to suppress direct user-facing announce unless explicitly requested

## 4. Child Result Collection

Use `sessions_history` or equivalent session history reads when:

- the child result needs verification
- a child failed to write artifacts
- you need to reconstruct `report.md` or `result.json`

## 5. Cron

Use cron to keep the Orchestrator Session alive until the run is terminal.

Cron should target the Orchestrator Session and use non-user delivery for internal ticks.

When the run is terminal:

- disable or remove cron

## 6. User Messaging

Use the native message send tool only for explicit user-visible updates:

- start acknowledgement
- milestone update
- approval request
- blocker or failure
- final completion

Do not send internal bookkeeping as user-facing chat.
