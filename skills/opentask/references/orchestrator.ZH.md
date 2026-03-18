# Orchestrator 手册

[English Version](./orchestrator.md)

这个文件定义了 Orchestrator Session 从开始到结束必须做什么。

## 0. 启动前不变量

在写任何 workflow 或 run 文件之前，或调用任何非读取型 OpenClaw 工具之前：

1. 读完 `SKILL.md`、本文件、`registry.ZH.md` 和 `operations.ZH.md`
2. 解析出 registry root
3. 解析出当前 live session 元数据

在这些读取完成之前，不要调用 `sessions_list`、`sessions_spawn`、cron 工具或消息发送工具。
如果在读完 `operations.ZH.md` 之前就出现了 `sessions_list` 或任何其他非读取型 OpenClaw 工具调用，那么这次启动应视为协议无效；必须先把启动顺序重新走对，再去写文件或派发执行。
如果这次无效启动已经为当前尝试创建了半成品 workflow 或 run 产物，重启前必须先删除或修复它们。在同一条失败尝试里晚点再读 `operations.ZH.md`，并不能让原来的 bootstrap 重新合法。
在 run 创建或绑定完成之前，不要开始任何实质性任务执行。run 之前的阶段只允许做启动读取、registry/session 解析、用于确定工作流形状的最小发现，以及 scaffolding。
一旦开始做 scaffolding，就不要留下半截状态。创建 run 的这一轮里，也必须同时创建 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl`、`control.jsonl`、节点目录和标准 node-local working-memory 元数据。
一个新 `runs/<runId>/` 路径里的第一笔写入必须来自 helper `scaffold`。不要手工预建 run 目录、`workflow.lock.md` 或任何 runtime JSON/JSONL 文件。

registry root 规则：

- 如果配置了 `OPENTASK_REGISTRY_ROOT`，优先使用它
- 否则使用当前 OpenClaw agent 的 workspace 根目录
- 对真实用户工作流，不要新建一个临时 repo，也不要把 shared skill 安装目录当作 registry root
- 只有操作者明确要求做隔离 skill 验证时，才使用临时测试目录
- 当你在运行时 prompt 或 child handoff 里写 `Workspace root` 时，它必须等于这个 registry root。`runs/...`、`workflows/...` 这类相对路径都从这里解析。

session 元数据规则：

- 在写 `state.json` 或 `refs.json` 之前，必须从当前 live session 解析出 `sourceSessionKey`、`rootSessionKey`、`sourceAgentId` 和 `deliveryContext`
- 如果这些值无法可靠解析，就停止并要求操作者修复环境，不要猜

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
- 当节点本身是多步骤任务时，把节点级 plan / progress / findings 写进规范节点文件
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
2. 只查看足以决定工作流形状的上下文。
3. 决定任务需要 crawl、直接执行，还是 subagent。
4. 写工作流文件。
5. 创建 run 目录和初始状态。
6. 开始执行。

不要在 planning 阶段就开始真正执行任务。Planning 只应收集足够定义工作流、依赖和执行分支的信息。
在 run 存在之前，不要做实质性调研、不要修改项目交付物、不要写最终报告、不要创建 subagent、不要配置 cron，也不要发送阶段性结果或里程碑更新。这些工作应放到 `gather-context`、执行节点或 delegated subagent 中，并且发生在 run 创建或绑定之后。
除非 assignment 明确要求，否则不要再加载其他 planning skill，也不要在 repo 根或旁路位置创建 `task_plan.md`、`findings.md`、`progress.md` 这类 planning memory 文件。OpenTask 的 workflow 文件、run registry 和规范的节点级 working-memory 文件才是规范工作记忆。

## 4. 什么时候要用 Crawl

在最终确定工作流之前，如果有以下情况，就先做 crawl 或广泛发现：

- 代码库结构未知
- 任务依赖很多文件的理解
- 任务需要对比多个文档或模块
- 在拆分任务前必须先收集证据

如果任务范围已经很明确、目标文件也已知，就不要用 crawl。

把 crawl 表达为一个 `session_turn` 节点，其 prompt 专门用于发现和产出上下文，例如 `gather-context`。

对于开放式调研任务，只做足够决定分支结构的前置发现。不要在 workflow 创建前就把 topic 调研做完；真正的调研应由 `gather-context` 和后续执行节点承担。

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
- `defaults.agentId` 要与实际拥有该 run 的 agent 一致
- 不要写死具体 `runId`
- 不要写死 `runs/<runId>/...` 路径
- 不要写死 session id 或 child session id
- 不要在 Markdown 正文里加入 `Run Information` 这类 run-local 元数据段落，也不要写 registry 路径、具体 run 状态等瞬时执行信息

具体的 run 路径、node id、依赖产物位置和输出目标，应在 run 创建之后，通过 run-local dispatch brief、节点本地 handoff 文件，或该次 run 的 `workflow.lock.md` 来补充。

必须包含：

- 一个或多个执行节点
- 用 `needs` 明确依赖
- 一个终态 `summary` 节点

节点类型用法：

- `session_turn`：由持久的节点绑定 session 执行；对真实 OpenTask run，默认应使用该节点的专用 workflow node session，而不是 root Orchestrator Session，除非操作者明确要求在 root session 内联执行
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
2. 优先直接让 `skills/opentask/scripts/registry_helper.py scaffold` 读取源 workflow frontmatter。只有在工作流形状需要显式 helper override 时，才写临时 JSON bootstrap spec
3. 如果这一轮 bootstrap 还没确认过 helper，可先运行 `python3 skills/opentask/scripts/registry_helper.py --help`
4. 运行 helper `scaffold`，由它创建 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl`、`control.jsonl`、节点目录和规范的节点级 working-memory 元数据；这是 `runs/<runId>/` 下第一笔合法写入
5. 通过 helper 管理的 scaffold，预先填好所有合适节点的 `artifactPaths` 和 `workingMemory`
6. 把当前 session 记录为：
   - `sourceSessionKey`
   - `rootSessionKey`
   - `sourceAgentId`
   - `deliveryContext`
7. 在派发任何节点之前，确认所有规范的节点级 working-memory 文件都已存在
8. 运行 helper `validate <runId>`
9. 在停止、等待或发送任何进度更新前，确认 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl` 和 `control.jsonl` 都已经存在

在开始任何实质执行之前，就应该先创建或绑定 run。如果你已经花了较多时间搜集资料、修改交付物或撰写结论，通常说明 workflow 早就该存在，而这些工作应该发生在对应节点内部。
如果 run bootstrap 中途被打断，必须先恢复并完成 scaffolding，然后才能追加 `node.started`、请求 driver review 或派发 child。
如果你发现之前某次尝试只创建了源 workflow，或者只创建了 `runs/<runId>/nodes/`，就把这个 run 视为 bootstrap 未完成，先修复缺失 scaffold，再做任何其他事情。

## 8. 执行循环

每次 orchestration pass 都按这个顺序：

1. 读取 `workflow.lock.md`、`state.json`、`refs.json` 和待处理 controls
2. 先检查 running 节点
3. 把依赖满足的节点提升为 `ready`
4. 派发 ready 节点
5. 通过 helper 更新状态和事件。事件时间戳必须单调递增，绝不能先写某个节点的 `node.started` 再写它的 `node.ready`
6. 判断是否应该通知用户
7. 如果 run 还没结束，确保 cron 还会再次唤醒 Orchestrator Session

每一次节点状态迁移，都必须同时反映在 `state.json` 和 `events.jsonl` 里，而且应该通过 `transition-node` 来写，而不是直接 edit 文件。

不要伪造时间戳，也不要在 helper 已经写入权威生命周期记录后，再手工补写重复事件。如果某个生命周期迁移缺失或错误，就先有意识地修复当前状态，再重新调用 helper，而不是手写一条带猜测元数据的重复事件。

不要跳过 `session_turn`、`summary`、`wait` 或 `approval` 节点的生命周期事件。一个正常完成的节点通常应该有完整审计链：

- `node.ready`
- `node.started`
- `node.completed` 或 `node.failed`

## 9. 节点派发规则

### session_turn 节点

适用于由持久 named session 直接完成的工作。

对真实 OpenTask run，`session_turn` 节点默认应派发到该节点自己的专用 workflow node session。不要一边创建专用 node session，一边又在 root Orchestrator Session 里继续做同一个节点的实质工作。一个节点只能有一个真实执行者。

派发时的 execution brief 必须告诉执行者：

- run 路径
- node id
- 需要读取的依赖产物
- 需要写出的文件

可复用的源 workflow prompt 可以保持通用。具体的 `runs/<runId>/...` 路径应该写到 dispatch brief 或其他 run-local handoff 里，而不是写进版本化 workflow 定义本身。

在派发 `session_turn` 或 `summary` 节点前：

- 先确认 bootstrap 已完整，且 state 里已经带有该节点的规范 working-memory 路径
- 如果这个节点有专用 node session，先调用 helper `bind`
- 然后调用 helper `transition-node <runId> <nodeId> running`
- 如果这个节点被派发到专用 node session，那么派发后 root Orchestrator Session 就必须立即停止该节点的实质任务执行，只保留 orchestration、监控和审阅职责

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
- 规范的节点级 working-memory 文件（`plan.md`、`findings.md`、`progress.md`，以及存在时的 `handoff.md`）
- child 不得修改全局 run 文件
- 除非明确需要，否则 child 不应直接向用户播报

如果可能，源 workflow prompt 应保持通用。具体的 run-local 路径、输出目标和“禁止直接向用户播报”的规则，应在创建 child 前写进 handoff 或其他 run-local brief。

在 `refs.json` 中记录：

- 父 session 映射
- `childSessionKey`
- 可用时记录 child 的 `runId`

先用 helper `bind` 写 child session 映射，再用 helper `transition-node <runId> <nodeId> running`。

spawn child 时，父 session 还应该：

- 写出 `handoff.md`
- 只有当 child 启动前这个节点已经需要多步工作记录时，才创建 `plan.md`、`findings.md` 和 `progress.md`
- 记录本次派发实际使用的父 session key

## 10. Subagent 返回后怎么办

child 完成后：

1. 必要时读取 child session history
2. 验证 `report.md` 和 `result.json`
3. 如果节点本身是多步骤任务，也检查节点级 working-memory 文件
4. 如果缺失，就根据 child transcript 回填
5. 把节点标为 `completed` 或 `failed`
6. 用 helper `transition-node` 追加对应事件并更新状态
7. 重新计算哪些下游节点会变成 `ready`
8. 决定是否需要增节点、重试、跳过或 rewiring

当 child 成功返回时：

- 让 `artifactPaths` 与实际已存在的文件保持一致
- 如果存在 `result.json`，就把它列进 `artifactPaths`
- 对每个刚刚变得可运行的下游节点，写一条 `node.ready`

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
2. 通过 helper 更新 `state.json` 和 `events.jsonl`
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

内部 cron orchestration 不应依赖用户可见的 announce 投递。cron 应静默唤醒 orchestrator，只有在上面列出的场景里才通过显式 progress message 给用户发更新。

## 14. 完成条件

当所有节点都进入终态时，run 完成。

然后：

1. 写最终 summary 产物
2. 对终态节点调用 helper `transition-node`，让 helper 自动把 run 状态推进到 `completed` 或 `failed`
4. 禁用或删除 cron
5. 发送最终用户可见更新
6. 如果发了最终可见消息，再调用 helper `progress`

在宣布完成之前，先做一次最终自检：

- run 需要的产物是否全部存在
- `control.jsonl` 是否为零字节空文件或合法 JSONL
- `events.jsonl` 是否为合法 JSONL、时间顺序正确，并且与节点生命周期迁移一致
- 最终 `workflow.lock.md`、`state.json` 与各节点产物中的依赖和终态是否一致
- helper `validate <runId>` 是否通过

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

如果某个节点显然执行了多步工作，但没有留下期望的 `plan.md`、`findings.md`、`progress.md` 或 `handoff.md`，父 session 还应回填这些规范 working-memory 文件。
