# Native Operations

[中文版本](./operations.ZH.md)

Use native OpenClaw tools and file edits. Do not assume the OpenTask backend or CLI is available.

Before the first non-read tool call for a real run, read this file in addition to `orchestrator.md` and `registry.md`.
Session discovery comes after this read. If you already called `sessions_list` before reading `operations.md`, treat that attempt as invalid startup and restart the bootstrap sequence cleanly.
Do not continue from a partially initialized run after that mistake.
If the invalid startup already created a new `workflows/*.task.md` file or `runs/<runId>/` scaffold for this attempt, delete or repair those partial artifacts before restarting. Do not keep bootstrapping the same run after reading `operations.md` late.

## 1. Filesystem Work

Use normal file tools to:

- create `workflows/*.task.md`
- create `runs/<runId>/...`
- update `workflow.lock.md`, `state.json`, `refs.json`
- append lines to `events.jsonl`
- write `nodes/<nodeId>/plan.md`, `findings.md`, `progress.md`
- write `nodes/<nodeId>/handoff.md` for subagent nodes
- write `nodes/<nodeId>/report.md` and `result.json`

For a real user workflow, write these files under the stable registry root. Do not bootstrap the run inside a throwaway temporary repo unless the operator explicitly requested an isolated skill test.
Treat the registry root as the runtime working directory for orchestration prompts and child sessions. Do not point `cwd`, `Workspace root`, or relative run paths at the OpenTask source repo unless that repo is itself the active registry root.

When bootstrapping a run, create `control.jsonl` immediately as an empty file unless explicit control actions already exist. Do not write placeholder comments or prose into that file.

When creating `workflow.lock.md`, preserve the canonical YAML frontmatter workflow shape from the source workflow. Do not replace it with an ad hoc prose summary.
Keep the versioned source workflow reusable: do not write run-local registry paths, concrete `runId` values, or transient run status text into `workflows/*.task.md`.
If bootstrap is interrupted, resume file creation and finish scaffolding before you dispatch a node, append `node.started`, or request driver review.
Do not stop after creating only `workflows/*.task.md` or only `runs/<runId>/nodes/`; that is still an invalid bootstrap.

## 2. Session Discovery

Use `sessions_list` to resolve the current session entry and capture:

- `sessionKey`
- `agentId`
- `deliveryContext`

Do this before writing `state.json` or `refs.json`. Never guess `sourceSessionKey`, `rootSessionKey`, or `deliveryContext`.
Also resolve or confirm the actual agent workspace root before choosing where `workflows/` and `runs/` will live.
Until the run has been created or bound, do not start substantive task work. In particular, do not launch `sessions_spawn`, configure cron, write deliverable artifacts outside bootstrap scaffolding, or send milestone/result messages before the run exists.
If you are retrying after an invalid startup inside the same conversation, repeat the ordered startup reads for the new attempt instead of assuming the previous read sequence still counts.

## 3. Subagent Creation

Use `sessions_spawn` when a node is delegated.

The child prompt should include:

- run path
- node id
- scoped task
- dependency artifacts to read
- canonical node-local working-memory paths to update
- required outputs to write
- a rule to avoid global state mutation
- a rule to suppress direct user-facing announce unless explicitly requested

Before spawning, ensure the node directory already contains the canonical `plan.md`, `findings.md`, `progress.md`, and `handoff.md` files.
Spawn the child with `cwd` set to the registry root so the run-local `runs/<runId>/...` paths resolve correctly.

## 4. Child Result Collection

Use `sessions_history` or equivalent session history reads when:

- the child result needs verification
- a child failed to write artifacts
- you need to reconstruct node-local working-memory files
- you need to reconstruct `report.md` or `result.json`

## 5. Cron

Use cron to keep the Orchestrator Session alive until the run is terminal.

Cron should target the Orchestrator Session and use non-user delivery for internal ticks.

When you create cron:

- store the real cron id returned by the tool in both `state.json` and `refs.json`
- avoid synthetic placeholder ids such as `cron-<runId>` unless that is the real tool return value
- keep internal tick prompts out of automatic user-facing announce delivery

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

## 7. Event Hygiene

Whenever you change node or run state:

- update `state.json`
- append the matching event to `events.jsonl`
- keep timestamps monotonic
- do not leave completed nodes without their matching lifecycle records
