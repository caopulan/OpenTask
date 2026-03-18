# 原生操作

[English Version](./operations.md)

优先使用 OpenClaw 原生工具、文件编辑和 `exec`，不要假设 OpenTask 后端或 repo 级 CLI 一定可用。

对真实 run 来说，在第一次执行非读取型工具调用之前，除了 `orchestrator.ZH.md` 和 `registry.ZH.md` 外，也要先读完本文件。
session 发现必须发生在这次读取之后。如果你在读 `operations.ZH.md` 之前就已经调用过 `sessions_list`，应把这次启动视为无效并重新按正确顺序启动 bootstrap。
出现这种情况后，不要继续沿用半初始化的 run；必须先中止并重启启动序列。
如果这次无效启动已经为当前尝试创建了新的 `workflows/*.task.md` 或 `runs/<runId>/` 半成品，那么重启前必须先删除或修复这些残留。不要通过“晚点再读 `operations.ZH.md`”继续同一条 bootstrap。

## 1. Runtime Helper

这个 skill 自带一个确定性的 helper：`skills/opentask/scripts/registry_helper.py`。

强制门槛：

1. 完成有序启动读取后的第一个非读取型工具调用，必须是：

```bash
python3 skills/opentask/scripts/registry_helper.py --help
```

2. 一个新 `runs/<runId>/` 路径下的第一笔写入必须来自 helper `scaffold`。
3. 不要手工创建 `runs/<runId>/`，哪怕只是空目录。
4. 不要手工写 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl`、`control.jsonl`。
5. 如果破坏了这道门槛，就隔离或删除这次无效 run 产物，然后从有序读取重新开始 bootstrap。

所有 runtime registry 变更都通过 OpenClaw 的 `exec` 调这个 helper：

- `scaffold`：创建 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl`、`control.jsonl`、节点目录和标准 node-local memory 文件
- `bind`：把 cron id、node session、child session、child run id 同步写进 `state.json` 和 `refs.json`
- `transition-node`：写节点生命周期迁移并追加匹配事件
- `progress`：把显式用户里程碑消息记到 registry
- `validate`：检查 scaffold 完整性、生命周期一致性，以及 `state.json` / `refs.json` 对齐情况

不要手工 edit `state.json`、`refs.json` 或 `events.jsonl`。这些都是 helper 管理的 runtime 文件。
如果你直接对这些 runtime 文件使用 `write` 或 `edit`，那么当前这次 run 尝试就是协议失效。继续之前，必须先删除或修复坏掉的 scaffold。

推荐命令序列：

```bash
python3 skills/opentask/scripts/registry_helper.py --help

# 直接写 workflows/<workflow-id>.task.md
# 可选：在 runs/ 目录之外写临时 spec JSON，例如 .opentask-bootstrap/<run-id>.spec.json

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> scaffold \
  --workflow-path workflows/<workflow-id>.task.md \
  --run-id <run-id> \
  --source-session-key <source-session-key> \
  --source-agent-id <agent-id> \
  --delivery-context-json '<delivery-context-json>'

# 只有在 workflow 需要显式 override spec 时才使用 --spec-file
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> scaffold \
  --workflow-path workflows/<workflow-id>.task.md \
  --spec-file .opentask-bootstrap/<run-id>.spec.json \
  --run-id <run-id> \
  --source-session-key <source-session-key> \
  --source-agent-id <agent-id> \
  --delivery-context-json '<delivery-context-json>'

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> bind <run-id> node-session \
  --node-id <node-id> \
  --value <node-session-key>

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> bind <run-id> child-session \
  --node-id <node-id> \
  --value <child-session-key>

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> bind <run-id> cron \
  --value <real-cron-id>

python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> transition-node <run-id> <node-id> running
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> transition-node <run-id> <node-id> completed
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> progress <run-id> "<发送给用户的消息>"
python3 skills/opentask/scripts/registry_helper.py --registry-root <registry-root> validate <run-id>
```

普通文件工具只用来：

- 创建可复用源 workflow：`workflows/*.task.md`
- 只有在 workflow frontmatter 需要显式 override 时，才写临时 JSON bootstrap spec 给 helper 使用，并且必须放在 `runs/<runId>/` 之外
- 只在确实需要补 run-local prompt 细节时编辑 `workflow.lock.md`
- 写 `nodes/<nodeId>/plan.md`、`findings.md`、`progress.md`
- 对于 subagent 节点，写 `nodes/<nodeId>/handoff.md`
- 写 `nodes/<nodeId>/report.md` 和 `result.json`

在 helper `scaffold` 成功之前，不要向 `runs/<runId>/` 下写任何其他文件。

对真实用户 workflow，这些文件必须写到稳定的 registry root 下。除非操作者明确要求做隔离 skill 测试，否则不要把 run 启动在一次性的临时 repo 里。
把 registry root 当作运行时工作目录。`cwd`、`Workspace root` 以及 `runs/<runId>/...`、`workflows/...` 这类相对路径都应该相对于这个根目录解析；除非 OpenTask 源码 repo 本身就是当前 registry root，否则不要把它当作运行目录。

初始化 run scaffold 时，要通过 helper `scaffold` 创建 `control.jsonl`；如果还没有任何显式动作，它必须是零字节空文件。不要往这个文件里写占位注释或普通说明文字。

创建 `workflow.lock.md` 时，要保留源工作流的 canonical YAML frontmatter 结构。不要把它改写成临时的纯文字摘要，也不要手工补写其他 runtime scaffold 文件。
版本化源 workflow 必须保持可复用：不要把 run-local 的 registry 路径、具体 `runId` 或瞬时 run 状态写进 `workflows/*.task.md`。
scaffolding 时不要手工编造假的时间戳或猜测性的生命周期元数据。让 helper 用真实写入时刻追加 runtime 时间戳。
如果 bootstrap 中途被打断，先继续补齐 scaffolding，再去派发节点、追加 `node.started` 或请求 driver review。
不要只创建 `workflows/*.task.md`，也不要只创建 `runs/<runId>/nodes/` 就停下；这种状态仍然属于无效 bootstrap。

## 2. Session 发现

用 `sessions_list` 找到当前 session 条目，并记录：

- `sessionKey`
- `agentId`
- `deliveryContext`

在运行 helper `scaffold` 之前先完成这一步。不要猜 `sourceSessionKey`、`rootSessionKey` 或 `deliveryContext`。
在决定 `workflows/` 和 `runs/` 写到哪里之前，也要先解析或确认真实的 agent workspace 根目录。
在 run 创建或绑定完成之前，不要开始任何实质性任务工作。尤其不要在 run 存在之前就启动 `sessions_spawn`、配置 cron、在 bootstrap scaffolding 之外写交付物产物，或发送里程碑/结果消息。
如果是在同一个对话里对一次无效启动做重试，也要为新的尝试重新按顺序读取启动文件，不要假设上一轮读取还算数。

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

在 spawn 前，先确保节点目录存在，并且已经写好 `handoff.md`。要把规范的 `plan.md`、`findings.md`、`progress.md` 路径传给 child，但除非节点已经需要多步工作记录，否则不要预创建这些占位文件。
spawn child 时，把 `cwd` 设为 registry root，这样 run-local 的 `runs/<runId>/...` 路径才能正确解析。
一旦 spawn 被接受，立即调用 helper `bind`，把 `childSessionKey` 和可用的 child `runId` 记到 registry 里。

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

- 通过 helper `bind` 把工具真实返回的 cron id 同时写进 `state.json` 和 `refs.json`
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
每次发出用户可见的里程碑消息后，都要调用 helper `progress`，把最后一次对外消息同步进 registry。

## 7. 事件卫生

每次改变节点或 run 状态时，都要：

- 使用 helper `transition-node`、`bind` 或 `progress`
- 保持时间戳单调递增
- 不要让 completed 节点缺失对应的生命周期记录
- 不要为 helper 或之前一次成功派发已经写过的生命周期迁移，再手工追加第二份重复记录
- 如果 helper 调用失败，就先重新读取文件并有意识地修复 scaffold 或状态，再重新调用 helper；不要靠猜字段继续执行，也不要在互相冲突的生命周期记录之上继续推进 run
