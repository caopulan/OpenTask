# Registry Spec

[中文版本](./registry-spec.ZH.md)

OpenTask uses a registry directory as the single source of truth. OpenClaw skills, the `opentask` CLI, the OpenTask backend, and the web UI all read or write this registry.

## Layout

```text
<registry-root>/
  workflows/
    *.task.md
  runs/
    <runId>/
      workflow.lock.md
      state.json
      refs.json
      events.jsonl
      control.jsonl
      nodes/
        <nodeId>/
          report.md
          result.json
```

## Workflow Definition

`workflows/*.task.md` uses Markdown with YAML frontmatter.

Required frontmatter fields:

- `workflowId`
- `title`
- `defaults`
- `driver`
- `nodes[]`

Each node must define:

- `id`
- `title`
- `kind`
- `needs`
- `prompt`
- `outputs`

Supported node kinds:

- `session_turn`
- `subagent`
- `wait`
- `approval`
- `summary`

Supported output modes:

- `notify`
- `report`

## Run State

`runs/<runId>/state.json` is the current projection for UI and operators.

Minimum fields:

- `runId`
- `workflowId`
- `title`
- `status`
- `sourceSessionKey`
- `sourceAgentId`
- `deliveryContext`
- `rootSessionKey`
- `cronJobId`
- `updatedAt`
- `nodes[]`

## Run Refs

`runs/<runId>/refs.json` tracks OpenClaw-specific runtime bindings.

Minimum fields:

- `runId`
- `sourceSessionKey`
- `sourceAgentId`
- `deliveryContext`
- `rootSessionKey`
- `cronJobId`
- `nodeSessions`
- `childSessions`
- `nodeRunIds`
- `appliedControlIds`

## Events

`runs/<runId>/events.jsonl` is append-only and is the audit trail.

Minimum event fields:

- `event`
- `timestamp`
- `runId`
- `nodeId` when applicable
- `message`
- `payload`

## Controls

`runs/<runId>/control.jsonl` is the only file for human or UI control intents.

Supported actions:

- `pause`
- `resume`
- `retry`
- `skip`
- `approve`
- `send_message`
- `patch_cron`

Each control record includes:

- `id`
- `action`
- `runId`
- `timestamp`
- `nodeId` when applicable
- `message` for `send_message`
- `patch` for `patch_cron`

## Node Output Contract

Each node may write:

- `report.md` for human-readable output
- `result.json` for structured status and session binding

`result.json` minimum fields:

- `runId`
- `nodeId`
- `status`
- `summary`
- `artifacts`
- `sessionKey`
- `childSessionKey`
- `payload`
