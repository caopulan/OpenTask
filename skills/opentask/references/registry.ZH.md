# Registry 协议

[English Version](./registry.md)

这个文件定义了 Orchestrator Session 必须创建和维护的文件。

## 1. 目录结构

```text
<repo-root>/
  workflows/
    <workflowId>.task.md
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

## 2. Workflow 文件

直接用 Markdown + YAML frontmatter 写工作流。

frontmatter 必填字段：

- `workflowId`
- `title`
- `defaults`
- `driver`
- `nodes`

节点必填字段：

- `id`
- `title`
- `kind`
- `needs`
- `prompt`
- `outputs`

允许的节点类型：

- `session_turn`
- `subagent`
- `wait`
- `approval`
- `summary`

允许的输出模式：

- `notify`
- `report`

## 3. 最小工作流示例

```md
---
workflowId: repo-audit
title: Repo audit
defaults:
  agentId: main
driver:
  cron: "*/2 * * * *"
nodes:
  - id: gather-context
    title: Gather context
    kind: session_turn
    needs: []
    prompt: Inspect the repository and write a short context report.
    outputs:
      mode: report
      requiredFiles:
        - nodes/gather-context/report.md
  - id: implement-fix
    title: Implement fix
    kind: subagent
    needs: [gather-context]
    prompt: Implement the required code changes and write a report.
    outputs:
      mode: report
      requiredFiles:
        - nodes/implement-fix/report.md
  - id: summary
    title: Summary
    kind: summary
    needs: [implement-fix]
    prompt: Summarize the completed workflow.
    outputs:
      mode: report
      requiredFiles:
        - nodes/summary/report.md
---
```

## 4. state.json

Orchestrator Session 必须保持 `state.json` 最新。

最小字段：

```json
{
  "runId": "run-123",
  "workflowId": "repo-audit",
  "title": "Repo audit",
  "status": "running",
  "sourceSessionKey": "agent:main:discord:channel:123",
  "sourceAgentId": "main",
  "deliveryContext": {
    "channel": "discord",
    "to": "channel:123"
  },
  "rootSessionKey": "agent:main:discord:channel:123",
  "cronJobId": "cron-123",
  "updatedAt": "2026-03-16T00:00:00Z",
  "nodes": []
}
```

`nodes` 里的每个节点应至少追踪：

- `id`
- `title`
- `kind`
- `status`
- `needs`
- `outputsMode`
- `sessionKey`
- `childSessionKey`
- `artifactPaths`
- `startedAt`
- `completedAt`

## 5. refs.json

`refs.json` 用于保存执行绑定关系。

最小字段：

```json
{
  "runId": "run-123",
  "sourceSessionKey": "agent:main:discord:channel:123",
  "sourceAgentId": "main",
  "deliveryContext": {
    "channel": "discord",
    "to": "channel:123"
  },
  "rootSessionKey": "agent:main:discord:channel:123",
  "cronJobId": "cron-123",
  "nodeSessions": {},
  "childSessions": {},
  "nodeRunIds": {},
  "appliedControlIds": []
}
```

## 6. events.jsonl

每行追加一个 JSON 对象，绝不要重写历史。

最小字段：

- `event`
- `timestamp`
- `runId`
- `nodeId`，如适用
- `message`
- `payload`

常见事件：

- `run.created`
- `node.ready`
- `node.started`
- `node.completed`
- `node.failed`
- `node.waiting`
- `node.added`
- `node.rewired`
- `run.completed`

## 7. control.jsonl

`control.jsonl` 用于显式用户或 UI 动作。

Orchestrator Session 应该读取它，但不需要为自己的正常内部工作写 control 记录。

如果还没有任何显式 control 动作，`control.jsonl` 可以是一个零字节空文件。

如果 `control.jsonl` 非空，那么每一行都必须是一个合法的 JSON 对象。不要在这个文件里写注释、标题或普通说明文字。

如果你只是需要它先存在，请创建空文件，而不是写一条占位文本。

支持的动作：

- `pause`
- `resume`
- `retry`
- `skip`
- `approve`
- `send_message`
- `patch_cron`

## 8. 节点文件

每个节点目录里可以有辅助文件，但以下两个是规范文件：

- `report.md`
- `result.json`

`result.json` 最小字段：

```json
{
  "runId": "run-123",
  "nodeId": "implement-fix",
  "status": "completed",
  "summary": "Implemented the requested change.",
  "artifacts": ["nodes/implement-fix/report.md"],
  "sessionKey": "agent:main:discord:channel:123",
  "childSessionKey": "agent:main:subagent:abc",
  "payload": {}
}
```

## 9. 修改规则

Orchestrator Session 允许直接写：

- `workflows/*.task.md`
- `runs/<runId>/workflow.lock.md`
- `runs/<runId>/state.json`
- `runs/<runId>/refs.json`
- `runs/<runId>/events.jsonl`
- `runs/<runId>/nodes/<nodeId>/report.md`
- `runs/<runId>/nodes/<nodeId>/result.json`

Subagent 除非父 session 明确授权，否则只应写节点本地文件。
