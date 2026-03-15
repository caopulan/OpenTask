---
workflowId: research-demo-zh
title: "Research demo workflow (ZH)"
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
    title: "收集上下文"
    kind: session_turn
    needs: []
    prompt: |
      收集这个工作流的核心上下文，并写出一份简洁报告。
    outputs:
      mode: report
      requiredFiles:
        - "nodes/gather-context/report.md"
  - id: parallel-review
    title: "并行复核"
    kind: subagent
    needs:
      - gather-context
    prompt: |
      从独立视角复核已收集的上下文，并记录关键风险。
    outputs:
      mode: report
      requiredFiles:
        - "nodes/parallel-review/report.md"
  - id: approval-gate
    title: "审批关卡"
    kind: approval
    needs:
      - parallel-review
    prompt: "在最终收尾前等待操作者批准。"
    outputs:
      mode: notify
  - id: wrap-up
    title: "汇总收尾"
    kind: summary
    needs:
      - approval-gate
    prompt: |
      汇总本次运行结果，并整理前面节点产出的内容。
    outputs:
      mode: report
      requiredFiles:
        - "nodes/wrap-up/report.md"
---

# Research Demo

[English](research-demo.task.md) | 中文

这个示例工作流展示了 OpenTask 第一版工作流格式：

- `session_turn` 用于主执行 session
- `subagent` 用于隔离式后续任务
- `approval` 用于由 UI 驱动的人工关卡
- `summary` 用于终态汇总

这个中文版本和英文版本使用同一套 schema，也可以单独作为 `workflowPath` 传给 OpenTask。
