# 原生操作

[English Version](./operations.md)

优先使用 OpenClaw 原生工具和文件编辑，不要假设 OpenTask 后端或 CLI 一定可用。

对真实 run 来说，在第一次执行非读取型工具调用之前，除了 `orchestrator.ZH.md` 和 `registry.ZH.md` 外，也要先读完本文件。
session 发现必须发生在这次读取之后。如果你在读 `operations.ZH.md` 之前就已经调用过 `sessions_list`，应把这次启动视为无效并重新按正确顺序启动 bootstrap。

## 1. 文件系统操作

用普通文件工具来：

- 创建 `workflows/*.task.md`
- 创建 `runs/<runId>/...`
- 更新 `workflow.lock.md`、`state.json`、`refs.json`
- 向 `events.jsonl` 追加一行
- 写 `nodes/<nodeId>/plan.md`、`findings.md`、`progress.md`
- 对于 subagent 节点，写 `nodes/<nodeId>/handoff.md`
- 写 `nodes/<nodeId>/report.md` 和 `result.json`

对真实用户 workflow，这些文件必须写到稳定的 registry root 下。除非操作者明确要求做隔离 skill 测试，否则不要把 run 启动在一次性的临时 repo 里。

初始化 run scaffold 时就创建 `control.jsonl`；如果还没有任何显式动作，就把它创建成零字节空文件。不要往这个文件里写占位注释或普通说明文字。

创建 `workflow.lock.md` 时，要保留源工作流的 canonical YAML frontmatter 结构。不要把它改写成临时的纯文字摘要。
版本化源 workflow 必须保持可复用：不要把 run-local 的 registry 路径、具体 `runId` 或瞬时 run 状态写进 `workflows/*.task.md`。
如果 bootstrap 中途被打断，先继续补齐 scaffolding，再去派发节点、追加 `node.started` 或请求 driver review。

## 2. Session 发现

用 `sessions_list` 找到当前 session 条目，并记录：

- `sessionKey`
- `agentId`
- `deliveryContext`

在写 `state.json` 和 `refs.json` 之前先完成这一步。不要猜 `sourceSessionKey`、`rootSessionKey` 或 `deliveryContext`。
在决定 `workflows/` 和 `runs/` 写到哪里之前，也要先解析或确认真实的 agent workspace 根目录。

## 3. 创建 Subagent

节点需要委派时，用 `sessions_spawn`。

child prompt 应包含：

- run 路径
- node id
- 有边界的任务范围
- 需要读取的依赖产物
- 需要更新的规范节点级 working-memory 路径
- 必须写出的输出文件
- 不得修改全局状态
- 除非明确要求，否则不要直接向用户播报

在 spawn 前，先确保节点目录里已经有规范的 `plan.md`、`findings.md`、`progress.md` 和 `handoff.md`。

## 4. 获取 Child 结果

以下情况使用 `sessions_history` 或等价 history 读取：

- 需要核实 child 结果
- child 没有写出产物
- 需要回填节点级 working-memory 文件
- 需要回填 `report.md` 或 `result.json`

## 5. Cron

用 cron 让 Orchestrator Session 一直活着，直到 run 进入终态。

cron 应该绑定 Orchestrator Session，并对内部 tick 使用非用户可见投递。

创建 cron 时：

- 把工具真实返回的 cron id 同时写进 `state.json` 和 `refs.json`
- 不要自己编一个 `cron-<runId>` 之类的占位 id，除非那正是工具的真实返回值
- 不要让内部 tick prompt 通过自动 announce 直接投递给用户

当 run 结束时：

- 禁用或删除 cron

## 6. 用户消息

只有在这些显式场景才使用原生 message send：

- 启动确认
- 里程碑更新
- 请求审批
- 阻塞或失败
- 最终完成

不要把内部记账或调度信息直接发给用户。

## 7. 事件卫生

每次改变节点或 run 状态时，都要：

- 更新 `state.json`
- 向 `events.jsonl` 追加匹配事件
- 保持时间戳单调递增
- 不要让 completed 节点缺失对应的生命周期记录
