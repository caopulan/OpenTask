# 快速上手

[English](QUICKSTART.md) | [项目总览](README.ZH.md)

这份教程会带你把一个真实的 OpenTask run 跑起来，并把运行态写到本地磁盘上。如果你的 OpenClaw Gateway 已经可用，完整流程通常不到 10 分钟。

## 你将获得什么

完成后你会得到：

- 运行在 `http://127.0.0.1:8000` 的后端
- 运行在 `http://127.0.0.1:5174/` 的 Web UI
- 至少一个由自由文本创建的 run
- 至少一个由示例工作流创建的 run
- 一份位于 `.opentask/runs/<runId>/` 的本地运行档案

## 1. 前置条件

开始前请确认：

- Python `3.12+`
- `uv`
- Node.js 与 `pnpm`
- 一个正在运行的 OpenClaw Gateway
- 一个名为 `opentask`、workspace 指向当前仓库的 OpenClaw agent

如果你的 Gateway 限制工具调用，请为 `opentask` agent 放开 `sessions_spawn`。`subagent` 节点依赖它。

## 2. 安装依赖

```bash
uv sync --dev
pnpm --dir web install
```

## 3. 确认 OpenClaw 连接

默认情况下，OpenTask 会复用本机 OpenClaw 的 device-auth 文件：

- `~/.openclaw/identity/device.json`
- `~/.openclaw/identity/device-auth.json`

如果你需要自定义配置，请在启动后端前导出环境变量：

```bash
export OPENTASK_GATEWAY_URL=ws://127.0.0.1:18789
export OPENTASK_AGENT_ID=opentask
export OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH=/path/to/device.json
export OPENTASK_GATEWAY_DEVICE_AUTH_PATH=/path/to/device-auth.json
```

## 4. 启动后端

```bash
uv run opentask-api
```

保持这个终端持续运行。然后验证 API 是否可访问：

```bash
curl http://127.0.0.1:8000/api/runs
```

## 5. 启动 Web UI

在第二个终端里执行：

```bash
pnpm --dir web dev
```

打开 [http://127.0.0.1:5174/](http://127.0.0.1:5174/)。Vite 开发服务器会把 `/api` 和 run stream WebSocket 自动代理到后端。

## 6. 用自由文本创建第一个 Run

直接调用 API：

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "title": "Quickstart free-form run",
    "taskText": "Inspect README.md and write a short report about what OpenTask does."
  }'
```

示例返回：

```json
{
  "runId": "opentask-1234abcd",
  "workflowId": "quickstart-free-form-run",
  "status": "running"
}
```

把返回的 `runId` 记下来。接下来你可以：

- 刷新 UI 并从列表打开这个 run
- 用 `GET /api/runs/<runId>/events` 查看事件日志
- 用 `tick` action 强制推进一轮调度

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/tick \
  -H 'content-type: application/json' \
  -d '{}'
```

## 7. 用示例工作流创建一个 Run

OpenTask 自带一个可直接运行的工作流示例：

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "workflowPath": "workflows/research-demo.task.md"
  }'
```

这个工作流展示了：

- 用于主执行链路的 `session_turn`
- 使用 `sessions_spawn` 的 `subagent`
- 依赖人工动作继续推进的 `approval` gate
- 负责终态汇总的 `summary` 节点

## 8. 查看并控制 Run

列出所有 run：

```bash
curl http://127.0.0.1:8000/api/runs
```

读取单个 run：

```bash
curl http://127.0.0.1:8000/api/runs/opentask-1234abcd
```

读取事件时间线：

```bash
curl http://127.0.0.1:8000/api/runs/opentask-1234abcd/events
```

暂停 run：

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/pause \
  -H 'content-type: application/json' \
  -d '{}'
```

恢复 run：

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/resume \
  -H 'content-type: application/json' \
  -d '{}'
```

批准示例工作流里的 gate：

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/approve \
  -H 'content-type: application/json' \
  -d '{
    "nodeId": "approval-gate"
  }'
```

重试某个节点：

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/retry \
  -H 'content-type: application/json' \
  -d '{
    "nodeId": "gather-context"
  }'
```

上面的动作在 Web UI 里也都有对应入口：run 列表、图视图、事件时间线和节点详情面板。

## 9. 查看运行档案

每个 run 都会写到 `.opentask/runs/<runId>/`。

关键文件包括：

- `workflow.lock.md`：冻结后的工作流快照
- `state.json`：API 和 UI 使用的当前状态投影
- `events.jsonl`：追加式审计日志
- `openclaw.json`：planner、driver、cron 和 node session 映射
- `nodes/<nodeId>/`：节点报告和节点级产物
- `.run.lock`：防止同一 run 被跨进程重复修改的锁文件

这意味着你不依赖 UI 也能排查运行状态，同时又能把运行态目录排除在 git 之外。

## 10. 常见问题

### `gateway error: device identity required`

说明 OpenClaw 的 device-auth 文件缺失或不可读。请检查：

- `~/.openclaw/identity/device.json`
- `~/.openclaw/identity/device-auth.json`

也可以通过 `OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH` 和 `OPENTASK_GATEWAY_DEVICE_AUTH_PATH` 指向其他文件。

### 新建 run 一直是 `running`，但节点没有推进

按这三个层次排查：

- 查看后端终端里有没有 Gateway 或解析错误
- 在 UI 时间线里看是否出现 `driver.requested`、`node.started`、`node.completed`
- 直接查看 `.opentask/runs/<runId>/events.jsonl`，它才是权威审计轨迹

### `subagent` 节点一开始就失败

通常是 OpenClaw Gateway 还没有对 `opentask` agent 放开 `sessions_spawn`。

### UI 能打开，但 API 请求失败

确认 `uv run opentask-api` 还在 `127.0.0.1:8000` 上运行。前端开发服务器默认就代理到这个地址。

## 下一步

- 读 [README.ZH.md](README.ZH.md) 了解整体架构和运行模型。
- 读 [workflows/research-demo.task.ZH.md](workflows/research-demo.task.ZH.md) 了解工作流 schema。
- 读 [web/README.ZH.md](web/README.ZH.md) 了解前端命令和说明。
