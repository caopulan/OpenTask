# Orchestrator 手册

[English Version](./orchestrator.md)

这个文件定义了 Orchestrator Session 从开始到结束必须做什么。

## 1. 角色定义

### Orchestrator Session

当前面向用户的 session 就是 Orchestrator Session。

它必须负责：

- 理解用户请求
- 判断是否需要工作流
- 构建和更新工作流
- 创建并维护 run 文件
- 派发 subagent 并吸收它们的结果
- 决定何时给用户发送可见进度消息

### Subagent Session

Subagent Session 是通过 `sessions_spawn` 创建的子执行上下文。

它必须：

- 只处理被分配的节点范围
- 只写节点本地产物
- 不修改全局工作流文件
- 把简洁、结构化的结果交还给父 session

## 2. 什么时候要启动工作流

满足以下任一条件时，启动工作流：

- 任务是多步骤的
- 任务大概率不止一个 agent turn
- 任务存在可并行的独立分支
- 任务需要显式等待、审批或重试
- 用户希望有审计轨迹或进度跟踪

如果只是一次性短回答，就不要启动工作流。

## 3. 规划流程

按以下顺序执行：

1. 解析用户目标和约束。
2. 查看现有上下文。
3. 决定任务需要 crawl、直接执行，还是 subagent。
4. 写工作流文件。
5. 创建 run 目录和初始状态。
6. 开始执行。

## 4. 什么时候要用 Crawl

在最终确定工作流之前，如果有以下情况，就先做 crawl 或广泛发现：

- 代码库结构未知
- 任务依赖很多文件的理解
- 任务需要对比多个文档或模块
- 在拆分任务前必须先收集证据

如果任务范围已经很明确、目标文件也已知，就不要用 crawl。

把 crawl 表达为一个 `session_turn` 节点，其 prompt 专门用于发现和产出上下文，例如 `gather-context`。

## 5. 什么时候要用 Subagent

出现以下情况时，创建 `subagent` 节点：

- 一个分支可以独立于主线程运行
- 任务需要隔离上下文
- 任务适合并行
- 任务需要产出一个清晰的可审阅交付物

对于琐碎工作，或者只涉及工作流记账的步骤，不要创建 subagent。

## 6. 如何构建工作流

工作流要明确且最小化。

把 `workflows/*.task.md` 下的版本化 workflow 当作可复用定义，而不是某次 run 的执行转录。

在源 workflow 里：

- prompt 只写任务范围和期望交付物
- 不要写死具体 `runId`
- 不要写死 `runs/<runId>/...` 路径
- 不要写死 session id 或 child session id

具体的 run 路径、node id、依赖产物位置和输出目标，应在 run 创建之后，通过 run-local dispatch brief、节点本地 handoff 文件，或该次 run 的 `workflow.lock.md` 来补充。

必须包含：

- 一个或多个执行节点
- 用 `needs` 明确依赖
- 一个终态 `summary` 节点

节点类型用法：

- `session_turn`：由 Orchestrator Session 或其他持久 session 直接完成
- `subagent`：委派隔离执行
- `wait`：显式等待
- `approval`：显式人工或用户 gate
- `summary`：最终总结

探索型任务建议模式：

1. `gather-context` 作为 `session_turn`
2. 一个或多个执行节点
3. 可选的 `approval`
4. `summary`

并行型任务建议模式：

1. `gather-context`
2. 多个并行节点，`needs: [gather-context]`
3. 一个依赖这些分支的 review 节点
4. `summary`

## 7. 创建 Run

当工作流准备好之后：

1. 选择一个 `runId`
2. 把工作流复制到 `runs/<runId>/workflow.lock.md`
3. 创建 `state.json`、`refs.json`、`events.jsonl`、`control.jsonl`
4. 把当前 session 记录为：
   - `sourceSessionKey`
   - `rootSessionKey`
   - `sourceAgentId`
   - `deliveryContext`
5. 把入口节点标成 `ready`
6. 追加 `run.created`

## 8. 执行循环

每次 orchestration pass 都按这个顺序：

1. 读取 `workflow.lock.md`、`state.json`、`refs.json` 和待处理 controls
2. 先检查 running 节点
3. 把依赖满足的节点提升为 `ready`
4. 派发 ready 节点
5. 更新状态和事件。事件时间戳必须单调递增，绝不能先写某个节点的 `node.started` 再写它的 `node.ready`
6. 判断是否应该通知用户
7. 如果 run 还没结束，确保 cron 还会再次唤醒 Orchestrator Session

## 9. 节点派发规则

### session_turn 节点

适用于父 session 或其他持久 named session 直接完成的工作。

派发时的 execution brief 必须告诉执行者：

- run 路径
- node id
- 需要读取的依赖产物
- 需要写出的文件

可复用的源 workflow prompt 可以保持通用。具体的 `runs/<runId>/...` 路径应该写到 dispatch brief 或其他 run-local handoff 里，而不是写进版本化 workflow 定义本身。

### subagent 节点

派发前：

1. 创建节点目录
2. 在节点 prompt 或节点本地 brief 文件里写清 handoff
3. 调用 `sessions_spawn`

child task 必须包含：

- 任务范围
- run 路径
- node id
- 必须写出的输出文件
- child 不得修改全局 run 文件
- 除非明确需要，否则 child 不应直接向用户播报

如果可能，源 workflow prompt 应保持通用。具体的 run-local 路径、输出目标和“禁止直接向用户播报”的规则，应在创建 child 前写进 handoff 或其他 run-local brief。

在 `refs.json` 中记录：

- 父 session 映射
- `childSessionKey`
- 可用时记录 child 的 `runId`

然后追加 `node.started`。

## 10. Subagent 返回后怎么办

child 完成后：

1. 必要时读取 child session history
2. 验证 `report.md` 和 `result.json`
3. 如果缺失，就根据 child transcript 回填
4. 把节点标为 `completed` 或 `failed`
5. 追加对应事件
6. 重新计算哪些下游节点会变成 `ready`
7. 决定是否需要增节点、重试、跳过或 rewiring

child 完成之后，只有 Orchestrator Session 可以修改全局工作流或 run 状态。

## 11. 工作流变更规则

只有在新的证据改变计划时才修改工作流。

允许的变更：

- 新增节点
- 重连依赖
- 把节点标成 skipped
- 把节点标成 failed 但允许 retry

每次变更都必须：

1. 更新 `workflow.lock.md`
2. 更新 `state.json`
3. 追加一个解释原因的审计事件

## 12. Session 交互规则

父到子：

- 用 `sessions_spawn` 创建新的隔离分支
- 需要连续上下文时，用持久 session turn 而不是 child

子到父：

- 返回简洁的最终结果
- 写节点本地产物
- 不写父级状态

父到用户：

- 只在用户应该知道时发显式进度消息

## 13. 什么时候给用户发送消息

只有这些情况才给用户发送可见消息：

- 工作流刚启动，用户需要知道任务已转成长任务
- 一个有意义的里程碑完成
- 需要审批或额外输入
- 工作流阻塞或失败
- 工作流结束

不要因为每次内部 tick、每次记账动作、每次 child 启动都给用户发消息。

## 14. 完成条件

当所有节点都进入终态时，run 完成。

然后：

1. 写最终 summary 产物
2. 把 run 状态设为 `completed` 或 `failed`
3. 追加 `run.completed`
4. 禁用或删除 cron
5. 发送最终用户可见更新

在宣布完成之前，先做一次最终自检：

- run 需要的产物是否全部存在
- `control.jsonl` 是否为零字节空文件或合法 JSONL
- `events.jsonl` 是否为合法 JSONL、时间顺序正确，并且与节点生命周期迁移一致
- 最终 `workflow.lock.md`、`state.json` 与各节点产物中的依赖和终态是否一致

## 15. 状态迁移规则

统一按这些规则迁移状态。

节点状态：

- `pending -> ready`：所有依赖都进入终态，并且足以继续
- `ready -> running`：节点已派发
- `running -> completed`：所需输出已验证
- `running -> failed`：执行失败，或所需输出无法恢复
- `ready -> waiting` 或 `running -> waiting`：显式进入 `wait` 或 `approval`
- `waiting -> completed`：等待或审批条件已满足
- `* -> skipped`：只能由 Orchestrator 明确决定

Run 状态：

- 只要还有非终态节点，就保持 `running`
- 只有显式外部暂停时才进入 `paused`
- 所有节点终态且没有失败时，进入 `completed`
- 当工作流无法成功完成时，进入 `failed`

## 16. 父子 Session 产物契约

child 运行前，父 session 应确保节点目录已存在。

child 运行后，父 session 必须验证：

- 对于 `report` 节点，`nodes/<nodeId>/report.md` 是否存在
- `nodes/<nodeId>/result.json` 是否存在，或者是否可以重建

如果需要重建，父 session 应创建 `result.json`，其中至少包含：

- run id
- node id
- 最终节点状态
- 简短 summary
- artifact 路径
- `sessionKey`
- `childSessionKey`
- 值得保留的原始 payload
