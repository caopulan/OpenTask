# Registry Spec

[中文版本](./registry-spec.ZH.md)

OpenTask uses a registry directory as the single source of truth. OpenClaw skills, the `opentask` CLI, the OpenTask backend, and the web UI all read or write this registry.

For real OpenClaw runs, this registry root should be a stable shared workspace such as the configured `OPENTASK_REGISTRY_ROOT` or the current agent workspace root. A temporary sandbox root is appropriate only for explicit skill validation.
In runtime prompts and subagent handoffs, `Workspace root` should point to this registry root so that relative `workflows/...` and `runs/...` paths resolve consistently.

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
          plan.md
          findings.md
          progress.md
          handoff.md
          report.md
          result.json
```

## Workflow Definition

`workflows/*.task.md` uses Markdown with YAML frontmatter.

The source workflow must remain reusable across runs. Do not hard-code a specific `runId`, `runs/<runId>/...` path, stale agent/session binding, or run-local metadata such as `Run Information`, concrete registry paths, or transient execution status into the versioned source workflow.

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

Each node may also expose `workingMemory` with canonical paths for:

- `plan`
- `findings`
- `progress`
- `handoff` for subagent nodes

`sourceSessionKey`, `rootSessionKey`, `sourceAgentId`, `deliveryContext`, and `cronJobId` should reflect the actual live OpenClaw bindings discovered for that run.

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

Lifecycle events should be complete and ordered. If a node reaches `completed` in `state.json`, the audit trail should still contain the corresponding readiness, start, and completion transitions unless the node was explicitly skipped.

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

- `plan.md` for node-local execution planning
- `findings.md` for node-local discoveries or source notes
- `progress.md` for node-local execution progress
- `handoff.md` for parent-to-child subagent briefs
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
- `workingMemory`
- `payload`

The canonical node-local working-memory files should be scaffolded before execution begins for node kinds that support them, even if they start out empty. Bootstrap is incomplete until those files exist, and the orchestrator should not dispatch the first node or append `node.started` before that check passes.
