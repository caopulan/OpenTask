# Orchestrator Playbook

[中文版本](./orchestrator.ZH.md)

This file defines what the Orchestrator Session must do from start to finish.

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
2. Inspect available context.
3. Decide whether the task needs crawl, direct execution, or subagents.
4. Write the workflow file.
5. Create the run folder and initial state.
6. Start execution.

## 4. When To Use Crawl

Use crawl or broad repository discovery before finalizing the workflow when:

- the codebase structure is unknown
- the task depends on understanding many files
- the task depends on comparing several documents or modules
- you need evidence before deciding how to split the work

Do not use crawl when the task is already tightly scoped and the needed files are known.

Represent crawl as a `session_turn` node whose prompt is focused on discovery and artifact creation, for example `gather-context`.

## 5. When To Use Subagents

Create a `subagent` node when:

- a branch can run independently from the main thread
- a task needs isolated context
- a task benefits from parallel execution
- a task needs a clearly scoped deliverable that the parent can review

Do not create a subagent for trivial work or for steps that only update workflow bookkeeping.

## 6. How To Build the Workflow

Build a workflow that is explicit and minimal.

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
4. Record the current session as:
   - `sourceSessionKey`
   - `rootSessionKey`
   - `sourceAgentId`
   - `deliveryContext`
5. Mark entry nodes as `ready`.
6. Append `run.created`.

## 8. Execution Loop

On each orchestration pass:

1. Read `workflow.lock.md`, `state.json`, `refs.json`, and pending controls.
2. Check running nodes first.
3. Promote newly satisfied nodes to `ready`.
4. Dispatch ready nodes.
5. Update state and events.
6. Decide whether the user should be informed.
7. Ensure cron will wake the Orchestrator Session again if the run is not terminal.

## 9. Dispatch Rules

### session_turn Node

Use when the parent session or a persistent named session should do the work directly.

The node prompt must tell the executor:

- the run path
- the node id
- dependency artifacts to read
- which files to write

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
- a rule that the child must not modify global run files
- a rule that the child should suppress direct user-facing announce unless explicitly needed

Record in `refs.json`:

- parent session mapping
- `childSessionKey`
- child `runId` if available

Append `node.started`.

## 10. After a Subagent Returns

When a child finishes:

1. Read the child session history if needed.
2. Verify `report.md` and `result.json`.
3. If files are missing, reconstruct them from the child transcript.
4. Mark the node `completed` or `failed`.
5. Append the matching event.
6. Recompute which downstream nodes become `ready`.
7. Decide whether to add, retry, skip, or rewire nodes.

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

## 14. Completion

A run is complete when all nodes are terminal.

Then:

1. write the final summary artifact
2. set the run status to `completed` or `failed`
3. append `run.completed`
4. disable or remove cron
5. send the final user-visible update

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
