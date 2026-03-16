# 原生操作

[English Version](./operations.md)

优先使用 OpenClaw 原生工具和文件编辑，不要假设 OpenTask 后端或 CLI 一定可用。

## 1. 文件系统操作

用普通文件工具来：

- 创建 `workflows/*.task.md`
- 创建 `runs/<runId>/...`
- 更新 `workflow.lock.md`、`state.json`、`refs.json`
- 向 `events.jsonl` 追加一行
- 写 `nodes/<nodeId>/plan.md`、`findings.md`、`progress.md`
- 对于 subagent 节点，写 `nodes/<nodeId>/handoff.md`
- 写 `nodes/<nodeId>/report.md` 和 `result.json`

如果 `control.jsonl` 需要先存在但还没有任何动作，就把它创建成空文件。不要往这个文件里写占位注释或普通说明文字。

## 2. Session 发现

用 `sessions_list` 找到当前 session 条目，并记录：

- `sessionKey`
- `agentId`
- `deliveryContext`

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

## 4. 获取 Child 结果

以下情况使用 `sessions_history` 或等价 history 读取：

- 需要核实 child 结果
- child 没有写出产物
- 需要回填节点级 working-memory 文件
- 需要回填 `report.md` 或 `result.json`

## 5. Cron

用 cron 让 Orchestrator Session 一直活着，直到 run 进入终态。

cron 应该绑定 Orchestrator Session，并对内部 tick 使用非用户可见投递。

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
