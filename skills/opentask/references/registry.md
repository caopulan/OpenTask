# Registry Protocol

[中文版本](./registry.ZH.md)

This file defines the files the Orchestrator Session must create and maintain.

## 1. File Layout

```text
<repo-root>/
  workflows/
    <workflowId>.task.md
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

## 2. Workflow File

Write the workflow directly as Markdown plus YAML frontmatter.

The versioned workflow under `workflows/*.task.md` should stay reusable across runs.

For workflow node prompts:

- describe task scope, dependencies, and expected deliverables
- do not hard-code a specific `runId`
- do not hard-code concrete `runs/<runId>/...` paths in the source workflow
- add concrete run-local paths later in `workflow.lock.md` or another run-local brief used at dispatch time

Required frontmatter fields:

- `workflowId`
- `title`
- `defaults`
- `driver`
- `nodes`

Required node fields:

- `id`
- `title`
- `kind`
- `needs`
- `prompt`
- `outputs`

Allowed node kinds:

- `session_turn`
- `subagent`
- `wait`
- `approval`
- `summary`

Allowed output modes:

- `notify`
- `report`

## 3. Minimal Workflow Example

```md
---
workflowId: repo-audit
title: Repo audit
defaults:
  agentId: main
driver:
  cron: "*/2 * * * *"
nodes:
  - id: gather-context
    title: Gather context
    kind: session_turn
    needs: []
    prompt: Inspect the repository and write a short context report.
    outputs:
      mode: report
      requiredFiles:
        - nodes/gather-context/report.md
  - id: implement-fix
    title: Implement fix
    kind: subagent
    needs: [gather-context]
    prompt: Implement the required code changes and write a report.
    outputs:
      mode: report
      requiredFiles:
        - nodes/implement-fix/report.md
  - id: summary
    title: Summary
    kind: summary
    needs: [implement-fix]
    prompt: Summarize the completed workflow.
    outputs:
      mode: report
      requiredFiles:
        - nodes/summary/report.md
---
```

## 4. state.json

The Orchestrator Session must keep `state.json` current.

Minimum fields:

```json
{
  "runId": "run-123",
  "workflowId": "repo-audit",
  "title": "Repo audit",
  "status": "running",
  "sourceSessionKey": "agent:main:discord:channel:123",
  "sourceAgentId": "main",
  "deliveryContext": {
    "channel": "discord",
    "to": "channel:123"
  },
  "rootSessionKey": "agent:main:discord:channel:123",
  "cronJobId": "cron-123",
  "updatedAt": "2026-03-16T00:00:00Z",
  "nodes": []
}
```

Each node in `nodes` should track:

- `id`
- `title`
- `kind`
- `status`
- `needs`
- `outputsMode`
- `sessionKey`
- `childSessionKey`
- `artifactPaths`
- `workingMemory`
- `startedAt`
- `completedAt`

`artifactPaths` should list the canonical artifact paths expected for that node, even before the files exist. Do not leave `artifactPaths` empty only because a node is still `pending` or `ready`.
`workingMemory` should point to canonical node-local execution files when the node kind supports them. For `session_turn`, `subagent`, and `summary` nodes, use `plan.md`, `findings.md`, and `progress.md`. For `subagent`, also expose `handoff.md`.

## 5. refs.json

`refs.json` stores execution bindings.

Minimum fields:

```json
{
  "runId": "run-123",
  "sourceSessionKey": "agent:main:discord:channel:123",
  "sourceAgentId": "main",
  "deliveryContext": {
    "channel": "discord",
    "to": "channel:123"
  },
  "rootSessionKey": "agent:main:discord:channel:123",
  "cronJobId": "cron-123",
  "nodeSessions": {},
  "childSessions": {},
  "nodeRunIds": {},
  "appliedControlIds": []
}
```

## 6. events.jsonl

Append one JSON object per line. Never rewrite history.

Append events in chronological order. Do not backdate a new event so that its timestamp is earlier than a line already written.

Minimum fields:

- `event`
- `timestamp`
- `runId`
- `nodeId` when relevant
- `message`
- `payload`

Common events:

- `run.created`
- `node.ready`
- `node.started`
- `node.completed`
- `node.failed`
- `node.waiting`
- `node.added`
- `node.rewired`
- `run.completed`

For a normal node lifecycle, keep both event order and timestamps consistent with state transitions:

- `node.ready` before `node.started`
- `node.started` before `node.completed` or `node.failed`
- when a node is added by mutation, write the mutation event before any readiness or start event for that node

## 7. control.jsonl

`control.jsonl` is for explicit user or UI actions.

The Orchestrator Session should read it, but it does not need to create control records for its normal internal work.

If there are no explicit control actions yet, `control.jsonl` may exist as a zero-byte file.

If `control.jsonl` is non-empty, every line must be a valid JSON object. Do not write comments, headings, or prose into this file.

If you only need the file to exist before the first action arrives, create an empty file instead of a placeholder line.

Supported actions:

- `pause`
- `resume`
- `retry`
- `skip`
- `approve`
- `send_message`
- `patch_cron`

## 8. Node Files

Each node directory may contain helper files. These are first-class canonical files for node-local execution memory:

- `plan.md`
- `findings.md`
- `progress.md`
- `handoff.md` for subagent nodes

These remain the canonical outcome files:

- `report.md`
- `result.json`

`result.json` minimum fields:

```json
{
  "runId": "run-123",
  "nodeId": "implement-fix",
  "status": "completed",
  "summary": "Implemented the requested change.",
  "artifacts": ["nodes/implement-fix/report.md"],
  "sessionKey": "agent:main:discord:channel:123",
  "childSessionKey": "agent:main:subagent:abc",
  "workingMemory": {
    "plan": "nodes/implement-fix/plan.md",
    "findings": "nodes/implement-fix/findings.md",
    "progress": "nodes/implement-fix/progress.md",
    "handoff": "nodes/implement-fix/handoff.md"
  },
  "payload": {}
}
```

## 9. Edit Rules

Allowed direct writes by the Orchestrator Session:

- `workflows/*.task.md`
- `runs/<runId>/workflow.lock.md`
- `runs/<runId>/state.json`
- `runs/<runId>/refs.json`
- `runs/<runId>/events.jsonl`
- `runs/<runId>/nodes/<nodeId>/plan.md`
- `runs/<runId>/nodes/<nodeId>/findings.md`
- `runs/<runId>/nodes/<nodeId>/progress.md`
- `runs/<runId>/nodes/<nodeId>/handoff.md`
- `runs/<runId>/nodes/<nodeId>/report.md`
- `runs/<runId>/nodes/<nodeId>/result.json`

Subagents should only write node-local files unless the parent explicitly instructs otherwise.
