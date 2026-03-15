---
workflowId: research-demo
title: "Research demo workflow"
defaults:
  agentId: opentask
  timeoutMs: 30000
driver:
  cron: "*/2 * * * *"
  wakeMode: now
  sessionKeyTemplate: "session:workflow:{run_id}:driver"
  plannerSessionKeyTemplate: "session:workflow:{run_id}:planner"
nodes:
  - id: gather-context
    title: "Gather context"
    kind: session_turn
    needs: []
    prompt: |
      Collect the primary context for this workflow and write a concise report.
    outputs:
      mode: report
      requiredFiles:
        - "nodes/gather-context/report.md"
  - id: parallel-review
    title: "Parallel review"
    kind: subagent
    needs:
      - gather-context
    prompt: |
      Review the gathered context from an independent angle and record key risks.
    outputs:
      mode: report
      requiredFiles:
        - "nodes/parallel-review/report.md"
  - id: approval-gate
    title: "Approval gate"
    kind: approval
    needs:
      - parallel-review
    prompt: "Wait for operator approval before finalizing."
    outputs:
      mode: notify
  - id: wrap-up
    title: "Wrap up"
    kind: summary
    needs:
      - approval-gate
    prompt: |
      Summarize the run outcome and stitch together the previous artifacts.
    outputs:
      mode: report
      requiredFiles:
        - "nodes/wrap-up/report.md"
---

# Research Demo

This sample workflow demonstrates the first version of the OpenTask format:

- `session_turn` for the primary execution session
- `subagent` for isolated follow-up work
- `approval` for UI-driven gating
- `summary` for terminal synthesis
