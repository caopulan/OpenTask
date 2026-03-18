# Registry 规范

[English Version](./registry-spec.md)

OpenTask 使用一个 registry 目录作为唯一真源。OpenClaw 的 skill、`opentask` CLI、OpenTask 后端以及网页前端都围绕这套目录读写。
对 OpenClaw 原生 skill 执行来说，`runs/<runId>/` 目录以及顶层 runtime 文件 `workflow.lock.md`、`state.json`、`refs.json`、`events.jsonl`、`control.jsonl` 应通过 `python3 skills/opentask/scripts/registry_helper.py ...` 来创建和修改；源 workflow 和节点本地产物仍可直接编辑。

对真实 OpenClaw run 来说，这个 registry root 应该是稳定共享的工作目录，比如配置好的 `OPENTASK_REGISTRY_ROOT` 或当前 agent 的 workspace 根目录。临时 sandbox root 只适用于显式 skill 验证。
在运行时 prompt 和 subagent handoff 里，`Workspace root` 也应该指向这个 registry root，这样相对的 `workflows/...`、`runs/...` 路径才能稳定解析。

## 目录结构

```text
<registry-root>/
  workflows/
    *.task.md
  runs/
    <runId>/
      workflow.lock.md
      state.json
      refs.json
      events.jsonl
      control.jsonl
      nodes/
        <nodeId>/
          plan.md
          findings.md
          progress.md
          handoff.md
          report.md
          result.json
```

## 工作流定义

`workflows/*.task.md` 采用 Markdown + YAML frontmatter。

源 workflow 必须保持可复用。不要在版本化源 workflow 里写死某个 `runId`、`runs/<runId>/...` 路径、过期的 agent/session 绑定，也不要写入 `Run Information`、具体 registry 路径或瞬时执行状态这类 run-local 元数据。

frontmatter 必填字段：

- `workflowId`
- `title`
- `defaults`
- `driver`
- `nodes[]`

每个节点必须定义：

- `id`
- `title`
- `kind`
- `needs`
- `prompt`
- `outputs`

支持的节点类型：

- `session_turn`
- `subagent`
- `wait`
- `approval`
- `summary`

支持的输出模式：

- `notify`
- `report`

## Run State

`runs/<runId>/state.json` 是给 UI 和操作者使用的当前投影状态。

最小字段：

- `runId`
- `workflowId`
- `title`
- `status`
- `sourceSessionKey`
- `sourceAgentId`
- `deliveryContext`
- `rootSessionKey`
- `cronJobId`
- `updatedAt`
- `nodes[]`

每个节点还可以带一个 `workingMemory` 对象，记录这些规范路径：

- `plan`
- `findings`
- `progress`
- subagent 节点的 `handoff`

`sourceSessionKey`、`rootSessionKey`、`sourceAgentId`、`deliveryContext` 和 `cronJobId` 都应反映该 run 实际解析得到的 OpenClaw live 绑定。

## Run Refs

`runs/<runId>/refs.json` 记录 OpenClaw 侧的运行绑定关系。

最小字段：

- `runId`
- `sourceSessionKey`
- `sourceAgentId`
- `deliveryContext`
- `rootSessionKey`
- `cronJobId`
- `nodeSessions`
- `childSessions`
- `nodeRunIds`
- `appliedControlIds`

## Events

`runs/<runId>/events.jsonl` 是追加写入的审计日志。

最小事件字段：

- `event`
- `timestamp`
- `runId`
- `nodeId`（如适用）
- `message`
- `payload`

生命周期事件必须完整且有序。如果 `state.json` 里某个节点已经 `completed`，那么除非它被显式 `skipped`，审计日志里也应该有对应的 `ready`、`started` 和 `completed`。

## Controls

`runs/<runId>/control.jsonl` 是人工和 UI 控制意图的唯一入口。

支持的动作：

- `pause`
- `resume`
- `retry`
- `skip`
- `approve`
- `send_message`
- `patch_cron`

每条 control 记录包含：

- `id`
- `action`
- `runId`
- `timestamp`
- `nodeId`（如适用）
- `message`，用于 `send_message`
- `patch`，用于 `patch_cron`

## 节点输出约定

每个节点可以写：

- `plan.md`，用于节点本地执行计划
- `findings.md`，用于节点本地发现或来源记录
- `progress.md`，用于节点本地执行进度
- `handoff.md`，用于父 session 写给 subagent 的 brief
- `report.md`，用于人读报告
- `result.json`，用于结构化状态和 session 绑定

`result.json` 最小字段：

- `runId`
- `nodeId`
- `status`
- `summary`
- `artifacts`
- `sessionKey`
- `childSessionKey`
- `workingMemory`
- `payload`

对于支持节点级 working memory 的节点类型，应先在 `workingMemory` 里声明规范路径，但不必在执行前就 scaffold 出占位的 `plan.md`、`findings.md`、`progress.md`。只有当节点确实需要多步工作记录时才创建这些文件。bootstrap 在 helper 创建完规范 run 文件和节点目录后就算完成。对于 `subagent` 节点，应在 spawn 前写好 `handoff.md`。
