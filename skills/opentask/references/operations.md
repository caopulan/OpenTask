# Native Operations

[中文版本](./operations.ZH.md)

Use native OpenClaw tools, file edits, and `exec`. Do not assume the OpenTask backend or repo-level CLI is available.

Before the first non-read tool call for a real run, read this file in addition to `orchestrator.md` and `registry.md`.
Session discovery comes after this read. If you already called `sessions_list` before reading `operations.md`, treat that attempt as invalid startup and restart the bootstrap sequence cleanly.
Do not continue from a partially initialized run after that mistake.
If the invalid startup already created a new `workflows/*.task.md` file or `runs/<runId>/` scaffold for this attempt, delete or repair those partial artifacts before restarting. Do not keep bootstrapping the same run after reading `operations.md` late.

## 1. Runtime Helper

The skill ships a deterministic helper at `skills/opentask/scripts/registry_helper.py`.

Mandatory gate:

1. The first non-read tool call after the ordered startup reads must be:

```bash
python3 skills/opentask/scripts/registry_helper.py --help
```

2. The first write beneath a new `runs/<runId>/` path must come from helper `scaffold`.
3. Do not create `runs/<runId>/` manually, even as an empty directory.
4. Do not write `workflow.lock.md`, `state.json`, `refs.json`, `events.jsonl`, or `control.jsonl` by hand.
5. If you break this gate, discard or quarantine the invalid run attempt and restart the bootstrap sequence from the ordered reads.

Use OpenClaw `exec` to run this helper for every runtime registry mutation:

- `scaffold` creates `workflow.lock.md`, `state.json`, `refs.json`, `events.jsonl`, `control.jsonl`, node directories, and canonical node-local memory files
- `bind` records cron ids, node sessions, child sessions, and child run ids in both `state.json` and `refs.json`
- `transition-node` writes node lifecycle changes and appends matching events
- `progress` records explicit user-facing milestone messages in the registry
- `validate` checks scaffold completeness, lifecycle consistency, and `state.json`/`refs.json` alignment

Do not hand-edit `state.json`, `refs.json`, or `events.jsonl`. They are helper-managed runtime files.
If you use `write` or `edit` on those runtime files directly, the current run attempt is invalid. Delete or repair the broken scaffold before you continue.

Recommended command sequence:

```bash
python3 skills/opentask/scripts/registry_helper.py --help

# write workflows/<workflow-id>.task.md directly
# optional: write scratch spec JSON outside runs/, for example .opentask-bootstrap/<run-id>.spec.json

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> scaffold \
  --workflow-path workflows/<workflow-id>.task.md \
  --run-id <run-id> \
  --source-session-key <source-session-key> \
  --source-agent-id <agent-id> \
  --delivery-context-json '<delivery-context-json>'

# only when the workflow needs an explicit override spec
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> scaffold \
  --workflow-path workflows/<workflow-id>.task.md \
  --spec-file .opentask-bootstrap/<run-id>.spec.json \
  --run-id <run-id> \
  --source-session-key <source-session-key> \
  --source-agent-id <agent-id> \
  --delivery-context-json '<delivery-context-json>'

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> bind <run-id> node-session \
  --node-id <node-id> \
  --value <node-session-key>

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> bind <run-id> child-session \
  --node-id <node-id> \
  --value <child-session-key>

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> bind <run-id> cron \
  --value <real-cron-id>

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> transition-node <run-id> <node-id> running
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> transition-node <run-id> <node-id> completed
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> progress <run-id> "<message shown to the user>"
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> validate <run-id>
```

Use normal file tools only to:

- create the reusable source workflow at `workflows/*.task.md`
- optionally write a temporary JSON bootstrap spec for the helper when the workflow frontmatter needs an explicit override; keep it outside `runs/<runId>/`
- edit `workflow.lock.md` only for legitimate run-local prompt specialization
- write `nodes/<nodeId>/plan.md`, `findings.md`, `progress.md`
- write `nodes/<nodeId>/handoff.md` for subagent nodes
- write `nodes/<nodeId>/report.md` and `result.json`

Until helper `scaffold` succeeds, do not write anything else under `runs/<runId>/`.

For a real user workflow, write these files under the stable registry root. Do not bootstrap the run inside a throwaway temporary repo unless the operator explicitly requested an isolated skill test.
Treat the registry root as the runtime working directory for orchestration prompts and child sessions. Do not point `cwd`, `Workspace root`, or relative run paths at the OpenTask source repo unless that repo is itself the active registry root.

When bootstrapping a run, use helper `scaffold`; it must create `control.jsonl` immediately as an empty file unless explicit control actions already exist. Do not write placeholder comments or prose into that file.

When creating `workflow.lock.md`, preserve the canonical YAML frontmatter workflow shape from the source workflow. Do not replace it with an ad hoc prose summary, and do not hand-author the rest of the scaffold around it.
Keep the versioned source workflow reusable: do not write run-local registry paths, concrete `runId` values, or transient run status text into `workflows/*.task.md`.
Do not hand-author synthetic timestamps or guessed lifecycle metadata while scaffolding. Let the helper append runtime timestamps from the real write-time clock.
If bootstrap is interrupted, resume file creation and finish scaffolding before you dispatch a node, append `node.started`, or request driver review.
Do not stop after creating only `workflows/*.task.md` or only `runs/<runId>/nodes/`; that is still an invalid bootstrap.

## 2. Session Discovery

Use `sessions_list` to resolve the current session entry and capture:

- `sessionKey`
- `agentId`
- `deliveryContext`

Do this before running helper `scaffold`. Never guess `sourceSessionKey`, `rootSessionKey`, or `deliveryContext`.
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
Immediately after the spawn is accepted, call helper `bind` to record `childSessionKey` and any child `runId`.

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

- store the real cron id returned by the tool via helper `bind` so it lands in both `state.json` and `refs.json`
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
After a visible milestone update is sent, call helper `progress` so the registry records the last message shown to the user.

## 7. Event Hygiene

Whenever you change node or run state:

- use helper `transition-node`, `bind`, or `progress`
- keep timestamps monotonic
- do not leave completed nodes without their matching lifecycle records
- do not append a second hand-authored copy of a lifecycle transition that was already written by the helper or a previous successful dispatch
- if a helper call fails, reread the files, repair the invalid scaffold or transition deliberately, and rerun the helper; do not continue execution on top of conflicting lifecycle records
