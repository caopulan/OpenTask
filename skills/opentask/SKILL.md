---
name: opentask
description: Manage OpenTask registry-backed workflows for OpenClaw-native long-running tasks. Use when a conversation should become a persistent workflow that keeps running through OpenClaw sessions, subagents, and cron while remaining inspectable in the registry and OpenTask UI; also use when binding the current Discord or channel session as the root orchestrator, validating or creating workflows, creating or binding runs, appending explicit control actions, sending progress updates, or patching cron.
---

# OpenTask

[中文版本](./SKILL.ZH.md)

Treat OpenClaw as the execution plane and OpenTask as the registry plus control plane. Assume no other repo context is available.

## Read These First

Read these files in order before you plan or make any non-read tool call:

1. [references/orchestrator.md](./references/orchestrator.md)
2. [references/registry.md](./references/registry.md)
3. [references/operations.md](./references/operations.md)

Do not call `sessions_list`, write files, spawn a child, request driver review, or touch cron until all three references have been read in this order.
Treat `sessions_list` as a non-read tool call even when you are only using it for discovery. If it happens before `references/operations.md` is read, the startup attempt is invalid and must be restarted before you write or dispatch anything.
The only valid recovery from that mistake is: stop the current bootstrap, delete or repair any partial run/workflow artifacts created by that invalid attempt, then restart from step 1. Do not continue the same bootstrap by reading `operations.md` later.

For a real run, the startup action order should be:

1. read `SKILL.md` if it is not already in view
2. read `references/orchestrator.md`
3. read `references/registry.md`
4. read `references/operations.md`
5. only then call `sessions_list`
6. only then resolve the registry root
7. only then create or bind the run
8. only then begin task execution

For each new user request that invokes `opentask`, re-establish this ordered startup sequence for that run attempt by reading these files from disk again. Do not rely on older in-context copies of `SKILL.md`, `orchestrator.md`, `registry.md`, or `operations.md`, and do not assume an earlier read from an older turn still makes the current bootstrap valid.

Once you start run scaffolding, finish it in the same execution pass. Do not stop after writing only `workflows/*.task.md` or only node directories. A valid bootstrap must leave behind `workflow.lock.md`, `state.json`, `refs.json`, `events.jsonl`, `control.jsonl`, node directories, and canonical node-local working-memory files for every eligible node.

## Mandatory Bootstrap Gate

For a real run, the first non-read tool call after the ordered startup reads must be an `exec` call that confirms the helper is available:

```bash
python3 skills/opentask/scripts/registry_helper.py --help
```

Treat any other first non-read tool call as a protocol failure for that run attempt.

Before helper `scaffold` succeeds:

- do not create `runs/<runId>/` by hand
- do not write `workflow.lock.md`
- do not write `state.json`, `refs.json`, `events.jsonl`, or `control.jsonl`
- do not dispatch a node, spawn a child, configure cron, or send milestone updates

The only allowed pre-scaffold writes are:

- the reusable source workflow at `workflows/*.task.md`
- an optional scratch bootstrap spec JSON outside the run directory, for example `.opentask-bootstrap/<runId>.spec.json`, if you need helper `scaffold --spec-file`

If you violate this gate, stop, quarantine or delete the invalid run attempt, and restart from the ordered startup reads.

## Installation Assumption

Assume this `opentask` skill has been installed into the shared skills directory used by the current OpenClaw deployment.

If you cannot read this file or the linked references from the current session, stop and tell the operator that the skill is not installed for this agent yet.

## Core Model

- The current user-facing session becomes the Orchestrator Session.
- The Orchestrator Session plans the workflow, writes and updates registry files, spawns subagents, absorbs their results, and decides when to message the user.
- Subagents execute scoped work. They do not own the global workflow state.
- OpenTask UI and backend are optional control surfaces for humans. The agent must be able to operate using only OpenClaw native tools plus the file protocol in this skill.
- This skill ships a runtime helper at `skills/opentask/scripts/registry_helper.py`. Use OpenClaw `exec` to run that helper for run scaffolding and runtime registry mutations.
- The registry root for a real run is the stable OpenClaw workspace or configured `OPENTASK_REGISTRY_ROOT`. Do not create a fresh temporary repo or use the shared-skill install directory as the registry root for a real user task unless the operator explicitly asked for an isolated skill test.
- In runtime prompts and child handoffs, `Workspace root` means the registry root. Relative `runs/...` and `workflows/...` paths are resolved from that root, not from the OpenTask source repo.

## Keep These Rules

- Treat the current user-facing session as the root orchestrator session.
- Treat this skill and its linked references as the complete operating manual for the run. Do not load unrelated planning or workflow-management skills unless the user explicitly asks for them.
- Resolve the registry root and current session metadata before creating any workflow or run files. If you cannot resolve them reliably, stop and report the missing prerequisite instead of guessing.
- Before the run is created or bound, do not start any task execution. That includes deep research, repository edits for deliverables, writing final artifacts, spawning subagents, patching cron, requesting driver review, or sending substantive progress or result messages. The only allowed pre-run work is startup reads, session and registry discovery, minimal context inspection needed to shape the workflow, and workflow/run scaffolding.
- Keep the versioned source workflow reusable. Do not add run-local metadata sections such as `Run Information`, registry paths, concrete `runId` values, or transient status text to `workflows/*.task.md`; put those details in `workflow.lock.md`, node-local handoff files, or other run-local artifacts instead.
- Send user-visible progress through explicit updates; do not expose raw orchestration prompts.
- Let OpenClaw execute nodes and cron turns; let OpenTask record registry state and controls.
- Write the reusable source workflow and node-local artifacts directly when needed.
- Use helper `scaffold` as the only valid creator of `runs/<runId>/`, `workflow.lock.md`, `state.json`, `refs.json`, `events.jsonl`, and `control.jsonl`.
- Create and mutate `state.json`, `refs.json`, and `events.jsonl` through `python3 skills/opentask/scripts/registry_helper.py ...`; do not hand-edit those runtime files.
- Prefer letting `registry_helper.py scaffold` read the source workflow frontmatter directly. Only create a temporary JSON bootstrap spec when the workflow shape needs an explicit helper override; keep that spec outside the run directory and treat it as scratch input, not as a user-facing artifact.
- If you use `write` or `edit` directly on `runs/<runId>/state.json`, `refs.json`, or `events.jsonl`, that bootstrap or orchestration pass is invalid. Delete or repair the bad run artifacts, then restart the attempt with the helper.
- Do not fabricate or backdate timestamps, session keys, delivery metadata, cron ids, or lifecycle transitions. Use discovered values and the real write-time clock, or leave the field for the runtime layer to populate. If a lifecycle event already exists, do not append a second hand-authored copy of the same transition.
- Leave node outputs as `report.md` and `result.json`.
- For complex execution nodes, keep node-local working memory in `runs/<runId>/nodes/<nodeId>/plan.md`, `findings.md`, and `progress.md`; subagent handoffs belong in `handoff.md`.
- During run scaffolding, create `workflow.lock.md`, `state.json`, `refs.json`, `events.jsonl`, `control.jsonl`, node directories, canonical working-memory files, and complete initial node metadata before substantial execution begins.
- A partially created run directory is still a protocol failure. If you notice a run with only `nodes/` or only a source workflow file, repair the missing scaffold files before any further planning, research, user messaging, or dispatch.
- Do not dispatch the first node, append `node.started`, or request driver review until bootstrap is complete. If scaffolding is interrupted, repair the missing files first and only then continue execution.
- After a node has been dispatched to a dedicated node session or child session, the Orchestrator Session must stop doing that node's substantive task work itself. It may monitor, update registry state, handle controls, and review results, but it must not continue the same research, browsing, writing, or analysis in parallel from the root session.
- Internal cron turns are orchestration-only. They must not use user-visible announce delivery. Send user-facing updates only through explicit progress messages at meaningful milestones.
- Do not create extra root-level or sidecar planning-memory files such as `task_plan.md`, `findings.md`, or `progress.md` unless the current assignment explicitly requires them. Use the workflow/run registry plus canonical node-local memory files instead.
- Run `python3 skills/opentask/scripts/registry_helper.py validate <runId>` before declaring a bootstrap or terminal state complete. Treat validation failures as protocol bugs that must be repaired before you continue.
