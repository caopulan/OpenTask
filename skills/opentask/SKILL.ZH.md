# OpenTask

[English Version](./SKILL.md)

把 OpenClaw 视为执行平面，把 OpenTask 视为 registry 和控制平面，并假设你没有任何其他 repo 上下文。

## 先读这些文件

- 执行前必须先读 [references/orchestrator.ZH.md](./references/orchestrator.ZH.md)。
- 创建或更新 workflow/run 文件前必须读 [references/registry.ZH.md](./references/registry.ZH.md)。
- 需要知道原生 OpenClaw 工具如何使用时，再读 [references/operations.ZH.md](./references/operations.ZH.md)。

## 安装前提

默认这个 `opentask` skill 已经安装到了当前 OpenClaw 部署使用的 shared skills 目录中。

如果当前 session 连这个文件或上面的 references 都读不到，就应该立刻停止，并明确告诉操作者：这个 agent 还没有安装好 OpenTask skill。

## 核心模型

- 当前面向用户的 session 就是 Orchestrator Session。
- Orchestrator Session 负责规划工作流、写和更新 registry 文件、创建 subagent、吸收子任务结果，并决定何时给用户发消息。
- Subagent 只负责执行被分配的范围任务，不拥有全局工作流状态。
- OpenTask 的前后端只是给人用的控制面。即使没有这些部分，agent 也必须能够只靠 OpenClaw 原生工具和本 skill 里的文件协议继续运行。

## 保持这些规则

- 把当前面向用户的 session 当作 root orchestrator session。
- 把本 skill 及其 references 当作本次 run 的完整操作手册。除非用户明确要求，否则不要再加载其他 planning 或 workflow-management skill。
- 用户可见进度必须通过显式更新发送，不要暴露原始 orchestration prompt。
- 让 OpenClaw 执行节点和 cron，让 OpenTask 记录 registry 状态和 control。
- 必要时直接写 workflow 和 run 文件，不要依赖特殊的 OpenTask runtime 命令才能继续推进。
- 按 references 中定义的协议有意识地更新 `state.json`、`refs.json`、`events.jsonl`。
- 节点输出统一写成 `report.md` 和 `result.json`。
- 对于复杂执行节点，把节点级工作记忆写到 `runs/<runId>/nodes/<nodeId>/plan.md`、`findings.md`、`progress.md`；subagent 的父子 handoff 写到 `handoff.md`。
- 除非当前 assignment 明确要求，否则不要在 repo 根或旁路位置创建 `task_plan.md`、`findings.md`、`progress.md` 这类额外 planning memory 文件。应使用 workflow/run registry 和规范的节点级 working-memory 文件。
