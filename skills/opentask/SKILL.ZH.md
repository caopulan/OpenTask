# OpenTask Skill

[English Version](./SKILL.md)

当当前对话需要升级为一个可持续运行、可审计、可控的工作流时，使用这个 skill。

## 目标

把 OpenTask 当作一套 registry 契约和控制面：

- OpenClaw 负责执行。
- OpenTask UI 负责可视化和显式控制。
- `workflows/` 与 `runs/` 下的 registry 是共享真源。

## 适用场景

以下情况应使用这个 skill：

- 任务是多步骤或长时间运行
- 需要 subagent 或 cron 持续推进
- 用户希望保留跟踪、产物和人工控制能力
- 当前 Discord 或频道 session 要继续作为 root orchestrator

如果是当前回合就能完成的一次性回答，不要使用它。

## Session 绑定

创建 run 之前，先确定当前 session：

1. 使用 `sessions_list` 找到当前 session 条目。
2. 记录：
   - `sessionKey`
   - `agentId`
   - `deliveryContext`
3. 把这个 session 作为 root orchestrator session。

内部调度消息不能把原始 orchestration prompt 直接发回给用户。用户可见更新必须通过显式消息发送。

## 推荐流程

1. 在 `workflows/*.task.md` 下创建或更新工作流文件。
2. 使用下面命令校验：

   ```bash
   uv run opentask workflow validate workflows/example.task.md
   ```

3. 绑定当前 session 创建 run：

   ```bash
   uv run opentask run create \
     --workflow-path workflows/example.task.md \
     --source-session-key '<sessionKey>' \
     --source-agent-id '<agentId>' \
     --delivery-context-json '<json>'
   ```

4. 让 OpenClaw 通过 root session 和 cron 持续推进。
5. 用户需要干预时，再追加显式 control action。

## 控制命令

暂停或恢复：

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
```

节点级控制：

```bash
uv run opentask control retry <runId> --node-id <nodeId>
uv run opentask control skip <runId> --node-id <nodeId>
uv run opentask control approve <runId> --node-id <nodeId>
```

向原始 delivery context 发送显式更新：

```bash
uv run opentask control send_message <runId> --message "Progress update"
```

修改 cron 配置：

```bash
uv run opentask control patch_cron <runId> --patch-json '{"enabled": true}'
```

## 输出契约

Subagent 和节点执行器应该至少留下：

- `runs/<runId>/nodes/<nodeId>/report.md`
- `runs/<runId>/nodes/<nodeId>/result.json`

正式格式说明见 [registry-spec.ZH.md](../../docs/registry-spec.ZH.md)。
