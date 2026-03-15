# OpenTask Skill

[中文版本](./SKILL.ZH.md)

Use this skill when the current conversation should become a long-running, auditable workflow that OpenClaw can continue through cron and subagents.

## Goal

Treat OpenTask as a registry contract plus control surface:

- OpenClaw stays responsible for execution.
- OpenTask UI stays responsible for visualization and explicit control actions.
- The registry under `workflows/` and `runs/` is the shared source of truth.

## When To Use It

Use this skill when:

- the task is multi-step or long-running
- you need subagents or repeated cron ticks
- the user wants persistent tracking, artifacts, and operator controls
- the current Discord or channel session should remain the root orchestrator

Do not use it for one-off answers that can complete in the current turn.

## Session Binding

Before creating a run, resolve the current session binding:

1. Use `sessions_list` to identify the current session entry.
2. Capture:
   - `sessionKey`
   - `agentId`
   - `deliveryContext`
3. Treat that session as the root orchestrator session.

Internal orchestration messages must not be delivered back to the user verbatim. Use explicit progress sends instead.

## Preferred Flow

1. Create or update a workflow file under `workflows/*.task.md`.
2. Validate the workflow with:

   ```bash
   uv run opentask workflow validate workflows/example.task.md
   ```

3. Create the run bound to the current session:

   ```bash
   uv run opentask run create \
     --workflow-path workflows/example.task.md \
     --source-session-key '<sessionKey>' \
     --source-agent-id '<agentId>' \
     --delivery-context-json '<json>'
   ```

4. Let OpenClaw continue the run through the root session and cron.
5. If the user asks for intervention, use explicit control actions.

## Control Commands

Pause or resume:

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
```

Node-level control:

```bash
uv run opentask control retry <runId> --node-id <nodeId>
uv run opentask control skip <runId> --node-id <nodeId>
uv run opentask control approve <runId> --node-id <nodeId>
```

Send an explicit update to the source delivery context:

```bash
uv run opentask control send_message <runId> --message "Progress update"
```

Patch the cron job:

```bash
uv run opentask control patch_cron <runId> --patch-json '{"enabled": true}'
```

## Output Contract

Subagents and node executors should leave:

- `runs/<runId>/nodes/<nodeId>/report.md`
- `runs/<runId>/nodes/<nodeId>/result.json`

See the formal registry contract in [registry-spec.md](../../docs/registry-spec.md).
