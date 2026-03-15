---
name: opentask
description: Manage OpenTask registry-backed workflows for OpenClaw-native long-running tasks. Use when a conversation should become a persistent workflow that keeps running through OpenClaw sessions, subagents, and cron while remaining inspectable in the registry and OpenTask UI; also use when binding the current Discord or channel session as the root orchestrator, validating or creating workflows, creating or binding runs, appending explicit control actions, sending progress updates, or patching cron.
---

# OpenTask

[中文版本](./SKILL.ZH.md)

Treat OpenClaw as the execution plane and OpenTask as the registry plus control plane.

## Follow This Flow

1. Resolve the current session with `sessions_list`.
2. Capture `sessionKey`, `agentId`, and `deliveryContext`.
3. Create or update `workflows/*.task.md`.
4. Validate the workflow with `uv run opentask workflow validate ...`.
5. Create or bind the run with the current session as the root orchestrator.
6. Let OpenClaw continue the run through the root session, subagents, and cron.
7. Use explicit controls for operator intervention.

## Read These References Only When Needed

- Read [references/operations.md](./references/operations.md) for CLI commands, session binding, and control actions.
- Read [references/registry.md](./references/registry.md) for the registry layout, allowed edits, and node output contract.

## Keep These Rules

- Treat the current user-facing session as the root orchestrator session.
- Send user-visible progress through explicit updates; do not expose raw orchestration prompts.
- Let OpenClaw execute nodes and cron turns; let OpenTask record registry state and controls.
- Edit workflow files or append controls; do not hand-edit `state.json`, `refs.json`, or `events.jsonl`.
- Leave node outputs as `report.md` and `result.json`.
