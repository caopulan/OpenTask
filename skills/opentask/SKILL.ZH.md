# OpenTask

[English Version](./SKILL.md)

把 OpenClaw 视为执行平面，把 OpenTask 视为 registry 和控制平面，并假设你没有任何其他 repo 上下文。

## 先读这些文件

在开始规划，或执行任何非读取型工具调用之前，按这个顺序读完：

1. [references/orchestrator.ZH.md](./references/orchestrator.ZH.md)
2. [references/registry.ZH.md](./references/registry.ZH.md)
3. [references/operations.ZH.md](./references/operations.ZH.md)

在这三个引用文件按顺序全部读完之前，不要调用 `sessions_list`、不要写文件、不要派发 child、不要请求 driver review，也不要操作 cron。
即使只是为了发现当前会话信息，`sessions_list` 也属于非读取工具调用。如果它发生在读完 `references/operations.ZH.md` 之前，这次启动尝试就算协议无效，必须先重启启动流程，再去写文件或派发执行。
这类错误唯一允许的恢复方式是：停止当前 bootstrap，删除或修复这次无效尝试留下的半成品 run/workflow，再从第 1 步重新开始。不要指望“之后再补读 `operations.ZH.md`”就能让同一轮 bootstrap 继续有效。

对真实 run 来说，启动动作顺序应当是：

1. 如果当前视野里还没有，就先读 `SKILL.md`
2. 读 `references/orchestrator.ZH.md`
3. 读 `references/registry.ZH.md`
4. 读 `references/operations.ZH.md`
5. 只有在这之后才能调用 `sessions_list`
6. 再去解析 registry root
7. 然后创建或绑定 run
8. 只有在这之后才能开始任务执行

每当有新的用户请求要调用 `opentask` 时，都要为这次 run 尝试重新建立这套有序启动流程。不要假设之前某一轮 turn 里读过 references，就能让当前这次 bootstrap 自动合法。

一旦开始做 run scaffolding，就必须在同一轮执行里把它补齐。不要只写 `workflows/*.task.md`，也不要只建 `nodes/` 目录。合法的 bootstrap 必须同时留下 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl`、`control.jsonl`、节点目录，以及每个适用节点的标准 working-memory 文件。

## 安装前提

默认这个 `opentask` skill 已经安装到了当前 OpenClaw 部署使用的 shared skills 目录中。

如果当前 session 连这个文件或上面的 references 都读不到，就应该立刻停止，并明确告诉操作者：这个 agent 还没有安装好 OpenTask skill。

## 核心模型

- 当前面向用户的 session 就是 Orchestrator Session。
- Orchestrator Session 负责规划工作流、写和更新 registry 文件、创建 subagent、吸收子任务结果，并决定何时给用户发消息。
- Subagent 只负责执行被分配的范围任务，不拥有全局工作流状态。
- OpenTask 的前后端只是给人用的控制面。即使没有这些部分，agent 也必须能够只靠 OpenClaw 原生工具和本 skill 里的文件协议继续运行。
- 真实 run 使用的 registry root 应该是稳定的 OpenClaw workspace，或者配置好的 `OPENTASK_REGISTRY_ROOT`。除非操作者明确要求做隔离 skill 测试，否则不要为真实用户任务新建临时 repo，也不要把 shared skill 安装目录当作 registry root。
- 在运行时 prompt 和 child handoff 里，`Workspace root` 指的就是 registry root。`runs/...`、`workflows/...` 这类相对路径都应当相对于这个根目录解析，而不是相对于 OpenTask 源码 repo。

## 保持这些规则

- 把当前面向用户的 session 当作 root orchestrator session。
- 把本 skill 及其 references 当作本次 run 的完整操作手册。除非用户明确要求，否则不要再加载其他 planning 或 workflow-management skill。
- 在创建任何 workflow 或 run 文件之前，先解析出 registry root 和当前 session 元数据。如果不能可靠解析，就停止并报告缺失的前提条件，不要猜。
- 在 run 创建或绑定完成之前，不要开始任何任务执行。这包括深入调研、为交付物修改仓库、写最终产物、创建 subagent、修改 cron、请求 driver review，或发送实质性的进度/结果消息。run 之前唯一允许做的事情，是启动读取、session 和 registry 解析、为确定工作流形状所需的最小上下文检查，以及 workflow/run scaffolding。
- 版本化源 workflow 必须保持可复用。不要在 `workflows/*.task.md` 中加入 `Run Information` 之类的 run-local 元数据段落，也不要写 registry 路径、具体 `runId` 或瞬时状态文字；这些内容应放到 `workflow.lock.md`、节点 handoff 或其他 run-local 产物里。
- 用户可见进度必须通过显式更新发送，不要暴露原始 orchestration prompt。
- 让 OpenClaw 执行节点和 cron，让 OpenTask 记录 registry 状态和 control。
- 必要时直接写 workflow 和 run 文件，不要依赖特殊的 OpenTask runtime 命令才能继续推进。
- 按 references 中定义的协议有意识地更新 `state.json`、`refs.json`、`events.jsonl`。
- 节点输出统一写成 `report.md` 和 `result.json`。
- 对于复杂执行节点，把节点级工作记忆写到 `runs/<runId>/nodes/<nodeId>/plan.md`、`findings.md`、`progress.md`；subagent 的父子 handoff 写到 `handoff.md`。
- 在 run scaffolding 阶段就创建 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl`、`control.jsonl`、节点目录、规范 working-memory 文件，以及完整的初始节点元数据，然后再进入实质执行。
- 只创建出半截 run 目录也算协议失败。如果你发现某个 run 只有 `nodes/`，或者只有源 workflow 文件，没有完整 scaffold，就必须先修复缺失文件，再继续任何规划、调研、用户通知或节点派发。
- 在 bootstrap 完成前，不要派发第一个节点，不要追加 `node.started`，也不要请求 driver review。如果 scaffolding 中途被打断，必须先补齐缺失文件，再继续执行。
- 内部 cron turn 只用于 orchestration，不得使用用户可见的 announce 投递。只有在真正的里程碑节点上，才通过显式 progress message 给用户发更新。
- 除非当前 assignment 明确要求，否则不要在 repo 根或旁路位置创建 `task_plan.md`、`findings.md`、`progress.md` 这类额外 planning memory 文件。应使用 workflow/run registry 和规范的节点级 working-memory 文件。
