# Registry

[中文版本](./registry.ZH.md)

## Source of Truth

Use the registry as the only durable source of truth.

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

## What Each File Means

- `workflow.lock.md`: frozen workflow snapshot for the run
- `state.json`: UI and operator projection
- `refs.json`: OpenClaw runtime bindings such as source session, root session, cron, and child sessions
- `events.jsonl`: append-only audit trail
- `control.jsonl`: explicit operator or UI actions

## Allowed Manual Changes

Allowed:

- edit `workflows/*.task.md`
- append a new record to `control.jsonl`

Not allowed:

- hand-edit `state.json`
- hand-edit `refs.json`
- rewrite or delete `events.jsonl`

## Node Output Contract

For nodes that finish work, leave:

- `nodes/<nodeId>/report.md` for human-readable output
- `nodes/<nodeId>/result.json` for structured status and session binding

For the full project contract, read [../../../docs/registry-spec.md](../../../docs/registry-spec.md).
