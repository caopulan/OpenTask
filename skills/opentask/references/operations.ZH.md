# 操作参考

[English Version](./operations.md)

## Session 绑定

创建 run 之前先解析当前 session。

记录：

- `sessionKey`
- `agentId`
- `deliveryContext`

把这个 session 当作 root orchestrator。

## 工作流命令

校验工作流：

```bash
uv run opentask workflow validate workflows/example.task.md
```

## Run 命令

把当前 session 绑定进去创建 run：

```bash
uv run opentask run create \
  --workflow-path workflows/example.task.md \
  --source-session-key '<sessionKey>' \
  --source-agent-id '<agentId>' \
  --delivery-context-json '<json>'
```

重新绑定已有 run：

```bash
uv run opentask run bind <runId> \
  --source-session-key '<sessionKey>' \
  --source-agent-id '<agentId>' \
  --delivery-context-json '<json>'
```

## 控制命令

暂停或恢复：

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
```

重试、跳过或批准节点：

```bash
uv run opentask control retry <runId> --node-id <nodeId>
uv run opentask control skip <runId> --node-id <nodeId>
uv run opentask control approve <runId> --node-id <nodeId>
```

发送用户可见进度消息：

```bash
uv run opentask control send_message <runId> --message "Progress update"
```

修改 cron：

```bash
uv run opentask control patch_cron <runId> --patch-json '{"enabled": true}'
```

## 运维规则

人工介入优先使用控制命令，或者追加 `control.jsonl` 记录；不要手工改运行态投影文件。
