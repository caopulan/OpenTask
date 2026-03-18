# Registry 协议

[English Version](./registry.md)

这个文件定义了 Orchestrator Session 必须创建和维护的文件。

真实 run 使用的 registry root 必须稳定且共享：

- 如果配置了 `OPENTASK_REGISTRY_ROOT`，优先使用它
- 否则使用当前 OpenClaw agent 的 workspace 根目录
- 对真实用户 run，不要静默新建一个临时 repo
- 在运行时 prompt 和 child handoff 里，`Workspace root` 必须指向这个 registry root。`workflows/...`、`runs/...` 这类相对路径都从这里解析。

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
          plan.md
          findings.md
          progress.md
          handoff.md
          report.md
          result.json
```

runtime 所有权规则：

- `workflows/*.task.md` 是可复用源定义，可以直接编辑。
- `workflow.lock.md` 可以做本次 run 的局部特化。
- `state.json`、`refs.json`、`events.jsonl` 是 runtime 所有文件，必须通过 `skills/opentask/scripts/registry_helper.py` 创建或修改，不能手工 edit。
- `control.jsonl` 仍然是 UI 或操作者的控制入口。
- `runs/<runId>/` 目录本身在 bootstrap 阶段也归 helper 管理。对于一个新 run，不要手工创建这个目录或其顶层 runtime 文件；先让 `registry_helper.py scaffold` 来创建。
- `nodes/<nodeId>/*` 下的产物和 working-memory 文件可以由 orchestrator 或 child session 直接写。

## 2. Workflow 文件

直接用 Markdown + YAML frontmatter 写工作流。

`workflows/*.task.md` 下的版本化 workflow 应保持可复用，不要只服务某一次 run。

对于 workflow 节点 prompt：

- 描述任务范围、依赖和期望交付物
- 让 `defaults.agentId` 与真实拥有该 run 的 agent 一致
- 不要写死某个具体 `runId`
- 不要在源 workflow 里写死 `runs/<runId>/...` 路径
- 具体的 run-local 路径应在 `workflow.lock.md` 或派发时使用的 run-local brief 里补充

版本化源 workflow 的 Markdown 正文可以包含稳定的任务概览，但不能包含 run-local 元数据，例如：

- `Run Information`
- 具体的 registry 路径
- 具体的 `runId`
- `Created, awaiting execution` 之类的瞬时状态文字

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

## 3a. `workflow.lock.md` 约束

`workflow.lock.md` 是某次 run 的冻结工作流快照。

它必须保持与源 `workflows/*.task.md` 相同的“Markdown 正文 + YAML frontmatter”结构。

冻结 run 时允许做的调整：

- 在节点 prompt 中补充 run-local 路径或派发细节
- 填入具体的节点产物目标
- 在 frontmatter 之后补充 run-local 说明

禁止把 frontmatter 工作流替换成这类临时摘要格式：

- 自定义 `## run_id` 之类的章节
- 只有 bullet 的依赖摘要
- 没有 canonical frontmatter 字段的纯文字节点列表

如果源工作流已经是合法 frontmatter 结构，就把这套结构复制到 `workflow.lock.md`，然后只针对当前 run 做具体化。
run-local 的元数据和冻结说明应写在 `workflow.lock.md` 中，而不是反写回源 workflow。

## 4. state.json

Orchestrator Session 必须保持 `state.json` 最新。
实际操作上，应通过 `registry_helper.py scaffold`、`bind`、`transition-node` 和 `progress` 来完成，而不是直接编辑 `state.json`。

`sourceSessionKey`、`sourceAgentId`、`deliveryContext` 和 `rootSessionKey` 必须来自当前 run 的真实 session discovery。不要猜这些值，也不要随手写出 `webchat` 这类未真实解析得到的占位值。
`cronJobId` 也必须是 OpenClaw 真正返回的 live cron job id，不能自己猜一个名字或写合成值。

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
- `workingMemory`
- `startedAt`
- `completedAt`

`artifactPaths` 应该记录该节点的规范产物路径，即使文件还没有生成也应如此。不要仅仅因为节点还处于 `pending` 或 `ready`，就把 `artifactPaths` 留空。
让 `artifactPaths` 与实际产物保持同步。如果节点写了 `result.json`，就把它也列进去。
`workingMemory` 应该指向节点级规范工作记忆文件。对于 `session_turn`、`subagent` 和 `summary` 节点，使用 `plan.md`、`findings.md`、`progress.md`；对于 `subagent`，还应暴露 `handoff.md`。

## 5. refs.json

`refs.json` 用于保存执行绑定关系。
实际修改应通过 helper `bind` 完成，而不是直接 edit。

`refs.json` 里的绑定字段必须与 `state.json` 中基于真实 session discovery 得到的值一致。不要在没有先解析当前 session 的情况下伪造或默认填充这些字段。
`refs.json` 里的 cron 绑定字段也必须与 OpenClaw 真正返回的 cron 对象一致。

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
事件应通过 helper 追加，不要替换或手工重写已有行。

事件必须按时间顺序追加。不要为新事件写一个比前面已落盘行更早的时间戳。

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
- `run.failed`
- `run.paused`
- `run.resumed`

对于正常的节点生命周期，事件顺序和时间戳都必须与状态迁移一致：

- `node.ready` 必须早于 `node.started`
- `node.started` 必须早于 `node.completed` 或 `node.failed`
- 如果一个节点是通过 mutation 新增的，先写 mutation 事件，再写这个节点的 ready/start 事件

不要跳过那些“很快完成”的节点的生命周期事件。如果 `state.json` 里某个节点已经 completed，那么 `events.jsonl` 里通常也应该有对应的 `ready`、`started` 和 `completed`，除非该节点被显式 `skipped`。

## 7. control.jsonl

`control.jsonl` 用于显式用户或 UI 动作。

Orchestrator Session 应该读取它，但不需要为自己的正常内部工作写 control 记录。

在初始化 run scaffold 时就创建 `control.jsonl`。如果还没有任何显式 control 动作，它必须是一个零字节空文件。

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

每个节点目录里可以有辅助文件。下面这些是节点级工作记忆的一等规范文件：

- `plan.md`
- `findings.md`
- `progress.md`
- subagent 节点的 `handoff.md`

下面两个仍然是最终结果的规范文件：

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
  "workingMemory": {
    "plan": "nodes/implement-fix/plan.md",
    "findings": "nodes/implement-fix/findings.md",
    "progress": "nodes/implement-fix/progress.md",
    "handoff": "nodes/implement-fix/handoff.md"
  },
  "payload": {}
}
```

对于支持节点级 working memory 的节点类型，orchestrator 应在 run scaffolding 阶段先在 `workingMemory` 里声明这些规范路径。`plan.md`、`findings.md`、`progress.md` 应按需懒创建，只在节点真的开始多步工作时写出；对于 subagent，要在 spawn 前创建 `handoff.md`。
当 helper 创建出的规范 run 文件、节点目录和 `workingMemory` 元数据都到位后，run scaffolding 就算完成；在此之前，不要派发第一个节点，不要追加 `node.started`，也不要请求 driver review。

## 9. 修改规则

Orchestrator Session 允许直接写：

- `workflows/*.task.md`
- `runs/<runId>/workflow.lock.md`
- `runs/<runId>/state.json`
- `runs/<runId>/refs.json`
- `runs/<runId>/events.jsonl`
- `runs/<runId>/nodes/<nodeId>/plan.md`
- `runs/<runId>/nodes/<nodeId>/findings.md`
- `runs/<runId>/nodes/<nodeId>/progress.md`
- `runs/<runId>/nodes/<nodeId>/handoff.md`
- `runs/<runId>/nodes/<nodeId>/report.md`
- `runs/<runId>/nodes/<nodeId>/result.json`

Subagent 除非父 session 明确授权，否则只应写节点本地文件。
