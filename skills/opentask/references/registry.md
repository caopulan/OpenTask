# Registry Protocol

[中文版本](./registry.ZH.md)

This file defines the files the Orchestrator Session must create and maintain.

The registry root for a real run must be stable and shared:

- Prefer `OPENTASK_REGISTRY_ROOT` when configured.
- Otherwise use the current OpenClaw agent workspace root.
- Do not silently create a new temporary repo for a real user run.
- In runtime prompts and child handoffs, `Workspace root` must refer to this registry root. Relative `workflows/...` and `runs/...` paths are resolved from here.

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

Runtime ownership rule:

- `workflows/*.task.md` is the reusable source definition and may be edited directly.
- `workflow.lock.md` may be specialized for the run.
- `state.json`, `refs.json`, and `events.jsonl` are runtime-owned and must be created or mutated through `skills/opentask/scripts/registry_helper.py`, not by hand.
- `control.jsonl` remains the control surface for UI or operator actions.
- The `runs/<runId>/` directory itself is helper-owned at bootstrap time. For a new run, do not create that directory or its top-level runtime files manually; let `registry_helper.py scaffold` create them first.
- `nodes/<nodeId>/*` artifacts and working-memory files may be written directly by the orchestrator or child sessions.

## 2. Workflow File

Write the workflow directly as Markdown plus YAML frontmatter.

The versioned workflow under `workflows/*.task.md` should stay reusable across runs.

For workflow node prompts:

- describe task scope, dependencies, and expected deliverables
- keep `defaults.agentId` aligned with the real agent that owns the run
- do not hard-code a specific `runId`
- do not hard-code concrete `runs/<runId>/...` paths in the source workflow
- add concrete run-local paths later in `workflow.lock.md` or another run-local brief used at dispatch time

The Markdown body of the versioned source workflow may contain durable task overview sections, but it must not contain run-local metadata such as:

- `Run Information`
- a concrete registry path
- a concrete `runId`
- transient status text like `Created, awaiting execution`

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

## 3a. workflow.lock.md Contract

`workflow.lock.md` is the frozen run-local snapshot of the workflow definition.

It must keep the same Markdown plus YAML frontmatter shape as the source `workflows/*.task.md`.

Allowed changes when freezing a run:

- add run-local paths or dispatch-specific details inside node prompts
- fill concrete node-local artifact targets
- add run-local notes below the frontmatter body

Do not replace the frontmatter workflow with an ad hoc summary format such as:

- custom `## run_id` sections
- bullet-only dependency summaries
- prose-only node lists without canonical frontmatter fields

If the source workflow already has valid frontmatter, copy that structure into `workflow.lock.md` and only specialize it for the current run.
Put run-local metadata and freeze notes in `workflow.lock.md`, not back into the source workflow file.

## 4. state.json

The Orchestrator Session must keep `state.json` current.
In practice, that means calling `registry_helper.py scaffold`, `bind`, `transition-node`, and `progress` rather than editing `state.json` directly.

`sourceSessionKey`, `sourceAgentId`, `deliveryContext`, and `rootSessionKey` must come from actual session discovery for the current run. Do not guess these values and do not invent placeholders such as `webchat` when the session was not resolved that way.
`cronJobId` must be the actual live cron job identifier returned by OpenClaw, not a guessed or synthetic name.

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
Keep `artifactPaths` synchronized with actual outputs. If the node writes `result.json`, include it there.
`workingMemory` should point to canonical node-local execution files when the node kind supports them. For `session_turn`, `subagent`, and `summary` nodes, use `plan.md`, `findings.md`, and `progress.md`. For `subagent`, also expose `handoff.md`.

## 5. refs.json

`refs.json` stores execution bindings.
In practice, mutate it through helper `bind` instead of direct edits.

The binding fields in `refs.json` must match the same discovered live session metadata used in `state.json`. Never fabricate or default them without resolving the current session first.
The cron binding fields in `refs.json` must also match the actual cron object returned by OpenClaw.

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
Append through the helper; do not replace or hand-rewrite existing lines.

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
- `run.failed`
- `run.paused`
- `run.resumed`

For a normal node lifecycle, keep both event order and timestamps consistent with state transitions:

- `node.ready` before `node.started`
- `node.started` before `node.completed` or `node.failed`
- when a node is added by mutation, write the mutation event before any readiness or start event for that node

Do not skip lifecycle events for nodes that finish quickly. If `state.json` shows a node completed, `events.jsonl` should still contain the corresponding readiness, start, and completion records unless that node was explicitly skipped.

## 7. control.jsonl

`control.jsonl` is for explicit user or UI actions.

The Orchestrator Session should read it, but it does not need to create control records for its normal internal work.

Create `control.jsonl` during initial run scaffolding. If there are no explicit control actions yet, it must be a zero-byte file.

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

If a node kind supports node-local working memory, the orchestrator should declare those canonical paths in `workingMemory` during run scaffolding even before the node starts. Create `plan.md`, `findings.md`, and `progress.md` lazily when the node begins real multi-step work. For subagents, create `handoff.md` before spawn.
Run scaffolding is complete once the helper-created run files, node directories, and canonical `workingMemory` metadata exist. Do not dispatch the first node, append `node.started`, or request driver review before that bootstrap check passes.

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
