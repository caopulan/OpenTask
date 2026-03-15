---
name: opentask
description: Manage OpenTask registry-backed workflows for OpenClaw-native long-running tasks. Use when a conversation should become a persistent workflow that keeps running through OpenClaw sessions, subagents, and cron while remaining inspectable in the registry and OpenTask UI; also use when binding the current Discord or channel session as the root orchestrator, validating or creating workflows, creating or binding runs, appending explicit control actions, sending progress updates, or patching cron.
---

# OpenTask

[中文版本](./SKILL.ZH.md)

Treat OpenClaw as the execution plane and OpenTask as the registry plus control plane. Assume no other repo context is available.

## Read These First

- Always read [references/orchestrator.md](./references/orchestrator.md) before acting.
- Read [references/registry.md](./references/registry.md) before creating or updating workflow/run files.
- Read [references/operations.md](./references/operations.md) when you need native OpenClaw tool usage patterns.

## Core Model

- The current user-facing session becomes the Orchestrator Session.
- The Orchestrator Session plans the workflow, writes and updates registry files, spawns subagents, absorbs their results, and decides when to message the user.
- Subagents execute scoped work. They do not own the global workflow state.
- OpenTask UI and backend are optional control surfaces for humans. The agent must be able to operate using only OpenClaw native tools plus the file protocol in this skill.

## Keep These Rules

- Treat the current user-facing session as the root orchestrator session.
- Send user-visible progress through explicit updates; do not expose raw orchestration prompts.
- Let OpenClaw execute nodes and cron turns; let OpenTask record registry state and controls.
- Write workflow and run files directly when needed; do not depend on a special OpenTask runtime command to make progress.
- Update `state.json`, `refs.json`, and `events.jsonl` intentionally as part of the orchestration protocol described in the references.
- Leave node outputs as `report.md` and `result.json`.
