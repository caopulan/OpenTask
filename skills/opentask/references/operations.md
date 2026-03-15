# Operations

[中文版本](./operations.ZH.md)

## Session Binding

Resolve the current session before creating a run.

Capture:

- `sessionKey`
- `agentId`
- `deliveryContext`

Treat that session as the root orchestrator.

## Workflow Commands

Validate a workflow:

```bash
uv run opentask workflow validate workflows/example.task.md
```

## Run Commands

Create a run bound to the current session:

```bash
uv run opentask run create \
  --workflow-path workflows/example.task.md \
  --source-session-key '<sessionKey>' \
  --source-agent-id '<agentId>' \
  --delivery-context-json '<json>'
```

Rebind an existing run:

```bash
uv run opentask run bind <runId> \
  --source-session-key '<sessionKey>' \
  --source-agent-id '<agentId>' \
  --delivery-context-json '<json>'
```

## Control Commands

Pause or resume:

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
```

Retry, skip, or approve a node:

```bash
uv run opentask control retry <runId> --node-id <nodeId>
uv run opentask control skip <runId> --node-id <nodeId>
uv run opentask control approve <runId> --node-id <nodeId>
```

Send a user-visible progress update:

```bash
uv run opentask control send_message <runId> --message "Progress update"
```

Patch cron:

```bash
uv run opentask control patch_cron <runId> --patch-json '{"enabled": true}'
```

## Operator Rule

Use control commands or append `control.jsonl` records for interventions. Do not hand-edit the runtime projection files.
