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

For a real run, the startup action order should be:

1. read `SKILL.md` if it is not already in view
2. read `references/orchestrator.md`
3. read `references/registry.md`
4. read `references/operations.md`
5. only then call `sessions_list`
6. only then resolve the registry root
7. only then create or bind the run
8. only then begin task execution

## Installation Assumption

Assume this `opentask` skill has been installed into the shared skills directory used by the current OpenClaw deployment.

If you cannot read this file or the linked references from the current session, stop and tell the operator that the skill is not installed for this agent yet.

## Core Model

- The current user-facing session becomes the Orchestrator Session.
- The Orchestrator Session plans the workflow, writes and updates registry files, spawns subagents, absorbs their results, and decides when to message the user.
- Subagents execute scoped work. They do not own the global workflow state.
- OpenTask UI and backend are optional control surfaces for humans. The agent must be able to operate using only OpenClaw native tools plus the file protocol in this skill.
- The registry root for a real run is the stable OpenClaw workspace or configured `OPENTASK_REGISTRY_ROOT`. Do not create a fresh temporary repo or use the shared-skill install directory as the registry root for a real user task unless the operator explicitly asked for an isolated skill test.

## Keep These Rules

- Treat the current user-facing session as the root orchestrator session.
- Treat this skill and its linked references as the complete operating manual for the run. Do not load unrelated planning or workflow-management skills unless the user explicitly asks for them.
- Resolve the registry root and current session metadata before creating any workflow or run files. If you cannot resolve them reliably, stop and report the missing prerequisite instead of guessing.
- Before the run is created or bound, do not start any task execution. That includes deep research, repository edits for deliverables, writing final artifacts, spawning subagents, patching cron, requesting driver review, or sending substantive progress or result messages. The only allowed pre-run work is startup reads, session and registry discovery, minimal context inspection needed to shape the workflow, and workflow/run scaffolding.
- Keep the versioned source workflow reusable. Do not add run-local metadata sections such as `Run Information`, registry paths, concrete `runId` values, or transient status text to `workflows/*.task.md`; put those details in `workflow.lock.md`, node-local handoff files, or other run-local artifacts instead.
- Send user-visible progress through explicit updates; do not expose raw orchestration prompts.
- Let OpenClaw execute nodes and cron turns; let OpenTask record registry state and controls.
- Write workflow and run files directly when needed; do not depend on a special OpenTask runtime command to make progress.
- Update `state.json`, `refs.json`, and `events.jsonl` intentionally as part of the orchestration protocol described in the references.
- Leave node outputs as `report.md` and `result.json`.
- For complex execution nodes, keep node-local working memory in `runs/<runId>/nodes/<nodeId>/plan.md`, `findings.md`, and `progress.md`; subagent handoffs belong in `handoff.md`.
- During run scaffolding, create `workflow.lock.md`, `state.json`, `refs.json`, `events.jsonl`, `control.jsonl`, node directories, canonical working-memory files, and complete initial node metadata before substantial execution begins.
- Do not dispatch the first node, append `node.started`, or request driver review until bootstrap is complete. If scaffolding is interrupted, repair the missing files first and only then continue execution.
- Internal cron turns are orchestration-only. They must not use user-visible announce delivery. Send user-facing updates only through explicit progress messages at meaningful milestones.
- Do not create extra root-level or sidecar planning-memory files such as `task_plan.md`, `findings.md`, or `progress.md` unless the current assignment explicitly requires them. Use the workflow/run registry plus canonical node-local memory files instead.
