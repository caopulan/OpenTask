# Orchestrator Playbook

[中文版本](./orchestrator.ZH.md)

This file defines what the Orchestrator Session must do from start to finish.

## 0. Startup Invariants

Before you write any workflow or run file, or call any non-read OpenClaw tool:

1. Read `SKILL.md`, this file, `registry.md`, and `operations.md`.
2. Resolve the registry root.
3. Resolve the current live session metadata.

Do not call `sessions_list`, `sessions_spawn`, cron tools, or message-send tools until those reads are complete.
If `sessions_list` or any other non-read OpenClaw tool appears before `operations.md` is read, treat that startup attempt as protocol-invalid and restart the startup sequence cleanly before writing or dispatching anything.
Before a run is created or bound, do not begin substantive task execution. The pre-run phase is only for startup reads, registry/session resolution, minimal workflow-shaping discovery, and scaffolding.

Registry root rules:

- Prefer `OPENTASK_REGISTRY_ROOT` when it is configured.
- Otherwise use the current OpenClaw agent workspace root.
- For a real user workflow, do not create a fresh temporary repo and do not use the shared-skill install directory as the registry root.
- Only use a temporary test root when the operator explicitly asks for isolated skill validation.

Session metadata rules:

- Resolve `sourceSessionKey`, `rootSessionKey`, `sourceAgentId`, and `deliveryContext` from the current live session before writing `state.json` or `refs.json`.
- If those values cannot be resolved reliably, stop and ask the operator to fix the environment instead of guessing.

## 1. Role Definitions

### Orchestrator Session

The current user-facing session is the Orchestrator Session.

It must:

- understand the user request
- decide whether the request needs a workflow
- build and update the workflow
- create and maintain the run files
- dispatch subagents and follow up on their results
- decide when to send user-visible progress messages

### Subagent Session

A subagent session is a child execution context created by `sessions_spawn`.

It must:

- work only on the assigned node scope
- keep node-local planning/progress/findings in the canonical node files when the node spans multiple steps
- write node-local artifacts
- avoid mutating global workflow files
- return a concise structured outcome to the parent

## 2. When To Start a Workflow

Start a workflow when at least one is true:

- the task is multi-step
- the task will likely take more than one agent turn
- the task has independent branches that can run in parallel
- the task needs explicit waiting, approval, or retry behavior
- the user wants auditability or progress tracking

Do not start a workflow for a single short answer.

## 3. Planning Procedure

Follow this order.

1. Parse the user goal and constraints.
2. Inspect only enough context to decide the workflow shape.
3. Decide whether the task needs crawl, direct execution, or subagents.
4. Write the workflow file.
5. Create the run folder and initial state.
6. Start execution.

Do not execute the real task during planning. Planning should stop once you have enough information to define the workflow, dependencies, and execution branches.
Before the run exists, do not do substantive research, edit project deliverables, write final reports, spawn subagents, configure cron, or send milestone/result updates. That work belongs in `gather-context`, execution nodes, or delegated subagents after the run is created or bound.
Do not load unrelated planning skills or create extra root-level planning-memory files such as `task_plan.md`, `findings.md`, or `progress.md` unless the assignment explicitly asks for them. The OpenTask workflow files, run registry, and canonical node-local memory files are the canonical working memory.

## 4. When To Use Crawl

Use crawl or broad repository discovery before finalizing the workflow when:

- the codebase structure is unknown
- the task depends on understanding many files
- the task depends on comparing several documents or modules
- you need evidence before deciding how to split the work

Do not use crawl when the task is already tightly scoped and the needed files are known.

Represent crawl as a `session_turn` node whose prompt is focused on discovery and artifact creation, for example `gather-context`.

For open-ended research tasks, do just enough pre-run discovery to decide the branch structure. Do not exhaust the topic before the workflow exists; the substantive research should happen inside `gather-context` and downstream execution nodes.

## 5. When To Use Subagents

Create a `subagent` node when:

- a branch can run independently from the main thread
- a task needs isolated context
- a task benefits from parallel execution
- a task needs a clearly scoped deliverable that the parent can review

Do not create a subagent for trivial work or for steps that only update workflow bookkeeping.

## 6. How To Build the Workflow

Build a workflow that is explicit and minimal.

Treat the versioned workflow under `workflows/*.task.md` as reusable definition, not a run-local execution transcript.

In the source workflow:

- keep prompts scoped to the task and expected deliverable
- keep `defaults.agentId` aligned with the actual agent expected to own the run
- do not hard-code a concrete `runId`
- do not hard-code `runs/<runId>/...` paths
- do not hard-code session ids or child session ids
- do not add run-local metadata sections in the Markdown body such as `Run Information`, registry path blocks, concrete run status, or other transient execution notes

Add concrete run paths, node ids, dependency artifact locations, and write targets later in a run-local dispatch brief, node-local handoff file, or the frozen `workflow.lock.md` created for that run.

Always include:

- one or more execution nodes
- clear dependencies in `needs`
- a terminal `summary` node

Use these node kinds:

- `session_turn`: work in the Orchestrator Session or another persistent session
- `subagent`: delegated isolated work
- `wait`: explicit waiting state
- `approval`: explicit operator or user gate
- `summary`: final synthesis

Use this pattern when the task is exploratory:

1. `gather-context` as `session_turn`
2. one or more execution nodes
3. optional `approval`
4. `summary`

Use this pattern when the task has independent branches:

1. `gather-context`
2. multiple parallel nodes with `needs: [gather-context]`
3. optional review node that depends on those branches
4. `summary`

## 7. Create the Run

When the workflow is ready:

1. Choose a `runId`.
2. Copy the workflow into `runs/<runId>/workflow.lock.md`.
3. Create `state.json`, `refs.json`, `events.jsonl`, and `control.jsonl`.
4. Create each node directory and canonical node-local working-memory files before dispatch.
5. Fill `artifactPaths` and `workingMemory` for every eligible node up front.
6. Record the current session as:
   - `sourceSessionKey`
   - `rootSessionKey`
   - `sourceAgentId`
   - `deliveryContext`
7. Mark entry nodes as `ready`.
8. Append `run.created`.
9. Append a `node.ready` event for every entry node.
10. Verify that every canonical node-local working-memory file exists before dispatching anything.

Create or bind the run before you start any substantive execution work. If you are already spending significant time gathering sources, editing deliverables, or drafting conclusions, the workflow should normally already exist and that work should be happening inside the appropriate node.
If run bootstrap was interrupted, resume and finish scaffolding before you append `node.started`, request driver review, or dispatch a child.

## 8. Execution Loop

On each orchestration pass:

1. Read `workflow.lock.md`, `state.json`, `refs.json`, and pending controls.
2. Check running nodes first.
3. Promote newly satisfied nodes to `ready`.
4. Dispatch ready nodes.
5. Update state and events. Keep event timestamps monotonic, and never write `node.started` before the matching `node.ready`.
6. Decide whether the user should be informed.
7. Ensure cron will wake the Orchestrator Session again if the run is not terminal.

Every node transition must be reflected in both `state.json` and `events.jsonl`.

Do not skip lifecycle events for `session_turn`, `summary`, `wait`, or `approval` nodes. A completed node should normally have a complete audit chain such as:

- `node.ready`
- `node.started`
- `node.completed` or `node.failed`

## 9. Dispatch Rules

### session_turn Node

Use when the parent session or a persistent named session should do the work directly.

The dispatched execution brief must tell the executor:

- the run path
- the node id
- dependency artifacts to read
- which files to write

The reusable source workflow prompt may stay generic. Put concrete `runs/<runId>/...` paths into the dispatch brief or another run-local handoff, not into the versioned workflow definition.

Before dispatching a `session_turn` or `summary` node:

- verify that bootstrap is complete and the node-local working-memory files exist
- append `node.started`
- set the node status to `running`
- update `updatedAt`

### subagent Node

Before spawning:

1. Create the node directory.
2. Write a short handoff in the node prompt or a node-local brief file.
3. Call `sessions_spawn`.

The child task must include:

- the task scope
- the run path
- the node id
- required output files
- canonical node-local working-memory files (`plan.md`, `findings.md`, `progress.md`, and `handoff.md` when present)
- a rule that the child must not modify global run files
- a rule that the child should suppress direct user-facing announce unless explicitly needed

Keep the reusable workflow prompt generic if possible. Put concrete run-local paths, output targets, and the announce-suppression rule into the child handoff or another run-local brief before spawning the child.

Record in `refs.json`:

- parent session mapping
- `childSessionKey`
- child `runId` if available

Append `node.started`.

When spawning a child, the parent should also:

- write `handoff.md`
- precreate `plan.md`, `findings.md`, and `progress.md`
- record the actual parent session key used for the dispatch

## 10. After a Subagent Returns

When a child finishes:

1. Read the child session history if needed.
2. Verify `report.md` and `result.json`.
3. Review node-local working-memory files if the node scope was multi-step.
4. If files are missing, reconstruct them from the child transcript.
5. Mark the node `completed` or `failed`.
6. Append the matching event.
7. Recompute which downstream nodes become `ready`.
8. Decide whether to add, retry, skip, or rewire nodes.

When a child returns successfully:

- keep `artifactPaths` consistent with the files that now exist
- if `result.json` exists, list it in `artifactPaths`
- write `node.ready` for every downstream node that just became runnable

Only the Orchestrator Session may mutate the global workflow or run state after a child finishes.

## 11. Workflow Mutation Rules

Mutate the workflow only when new evidence changes the plan.

Allowed mutations:

- add a node
- rewire dependencies
- mark a node skipped
- mark a node failed and retryable

Whenever you mutate:

1. update `workflow.lock.md`
2. update `state.json`
3. append an audit event explaining why

## 12. Session Interaction Rules

Parent to child:

- use `sessions_spawn` for new isolated branches
- use persistent session turns when continuity matters more than isolation

Child to parent:

- return a concise final outcome
- write node-local artifacts
- do not write parent-level state

Parent to user:

- send explicit progress only when a user should know something

## 13. When To Message the User

Send a user-visible message only in these cases:

- the workflow starts and the user should know it is now long-running
- a meaningful milestone completes
- an approval or input is required
- the workflow is blocked or failed
- the workflow completes

Do not message the user for every internal tick, every bookkeeping change, or every child launch.

Internal cron orchestration should not rely on user-visible announce delivery. Use cron to wake the orchestrator quietly, then send an explicit progress message only when one of the cases above applies.

## 14. Completion

A run is complete when all nodes are terminal.

Then:

1. write the final summary artifact
2. set the run status to `completed` or `failed`
3. append `run.completed`
4. disable or remove cron
5. send the final user-visible update

Before you declare completion, run a final self-check:

- every required artifact for the run exists
- `control.jsonl` is either zero-byte or valid JSONL
- `events.jsonl` is valid JSONL, chronologically ordered, and consistent with node lifecycle transitions
- the final `workflow.lock.md`, `state.json`, and node artifacts agree on dependencies and terminal statuses

## 15. Status Transition Rules

Use these transitions consistently.

Node status:

- `pending -> ready` when all dependencies are terminal and successful enough to continue
- `ready -> running` when the node is dispatched
- `running -> completed` when required outputs are verified
- `running -> failed` when execution fails or required outputs cannot be recovered
- `ready -> waiting` or `running -> waiting` for explicit `wait` or `approval`
- `waiting -> completed` when the wait or approval condition is satisfied
- `* -> skipped` only by explicit orchestration decision

Run status:

- `running` while any node is non-terminal
- `paused` only when an explicit external pause applies
- `completed` when every node is terminal and no node failed
- `failed` when the workflow cannot complete successfully

## 16. Parent/Child Output Contract

Before a child runs, the parent should ensure the node directory exists.

After a child runs, the parent should verify:

- `nodes/<nodeId>/report.md` exists for `report` nodes
- `nodes/<nodeId>/result.json` exists or can be reconstructed

If reconstruction is needed, the parent should create `result.json` with:

- the run id
- the node id
- the final node status
- a short summary
- artifact paths
- `sessionKey`
- `childSessionKey`
- any raw payload worth preserving

Also reconstruct or backfill canonical working-memory files when the node clearly performed multi-step work but did not leave the expected `plan.md`, `findings.md`, `progress.md`, or `handoff.md`.
