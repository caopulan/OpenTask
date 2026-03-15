# Registry 规范

[English Version](./registry-spec.md)

OpenTask 使用一个 registry 目录作为唯一真源。OpenClaw 的 skill、`opentask` CLI、OpenTask 后端以及网页前端都围绕这套目录读写。

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
          report.md
          result.json
```

## 工作流定义

`workflows/*.task.md` 采用 Markdown + YAML frontmatter。

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
- `payload`
