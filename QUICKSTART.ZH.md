# 快速上手

[English](QUICKSTART.md) | [项目总览](README.ZH.md)

这份指南先展示推荐的 OpenClaw 原生路径，再展示可选的 OpenTask 后端与 UI。

## 你将得到什么

完成后你会得到：

- 一个通过校验的 `workflows/` 工作流文件
- 一个位于 `runs/<runId>/` 的运行目录
- 一个绑定到 root session、可由 OpenClaw cron 持续推进的工作流
- 一个可选的控制面，地址为 `http://127.0.0.1:8000` 和 `http://127.0.0.1:5174/`

## 1. 先把 Skill 安装到 OpenClaw

把 [skills/opentask](skills/opentask) 复制或软链接到当前 OpenClaw 部署配置的 shared skills 目录里，并以 `opentask` 作为安装名。

继续之前，先确认 agent 能通过这个已安装的 skill 读到 [skills/opentask/SKILL.ZH.md](skills/opentask/SKILL.ZH.md)。

## 2. 安装依赖

```bash
uv sync --dev
pnpm --dir web install
```

## 3. 设置 Registry Root

设置 OpenTask 要管理的 registry 根目录：

```bash
export OPENTASK_REGISTRY_ROOT=/path/to/opentask-registry
export OPENTASK_GATEWAY_URL=ws://127.0.0.1:18789
```

第一次本地使用时，直接把当前仓库目录当作 registry root 也可以。

## 4. 校验示例工作流

```bash
uv run opentask workflow validate workflows/research-demo.task.md
```

## 5. 解析当前 OpenClaw Session

在你希望任务长期运行的 OpenClaw 对话里：

1. 使用 [skills/opentask/SKILL.ZH.md](skills/opentask/SKILL.ZH.md)
2. 解析当前 `sessionKey`、`agentId` 和 `deliveryContext`
3. 把这个 session 作为 root orchestrator

手工示例值：

- `sessionKey`: `agent:main:discord:channel:1234567890`
- `agentId`: `main`
- `deliveryContext`: `{"channel":"discord","to":"channel:1234567890"}`

## 6. 绑定当前 Session 创建 Run

```bash
uv run opentask run create \
  --workflow-path workflows/research-demo.task.md \
  --source-session-key 'agent:main:discord:channel:1234567890' \
  --source-agent-id main \
  --delivery-context-json '{"channel":"discord","to":"channel:1234567890"}'
```

命令会输出包含 `runId` 的 JSON。

## 7. 查看 Registry

打开这个 run 目录：

```bash
ls runs/<runId>
```

你应该能看到：

- `workflow.lock.md`
- `state.json`
- `refs.json`
- `events.jsonl`
- `control.jsonl`
- `nodes/`

每个文件的约定见 [docs/registry-spec.ZH.md](docs/registry-spec.ZH.md)。

## 8. 发送显式控制动作

暂停或恢复：

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
```

发送用户可见的进度更新：

```bash
uv run opentask control send_message <runId> --message "Still running."
```

修改 cron：

```bash
uv run opentask control patch_cron <runId> --patch-json '{"enabled": true}'
```

## 9. 启动可选的后端

```bash
uv run opentask-api
```

后端会索引 registry，并在 `http://127.0.0.1:8000` 暴露控制 API。

常用接口：

- `GET /api/runs`
- `GET /api/runs/<runId>`
- `GET /api/runs/<runId>/events`
- `POST /api/runs/<runId>/actions/send_message`

## 10. 启动可选的 Web UI

```bash
pnpm --dir web dev
```

打开 [http://127.0.0.1:5174/](http://127.0.0.1:5174/)。

这个 UI 适合：

- 浏览 run 列表
- 查看 DAG 结构
- 检查节点产物和 session 绑定
- 发起显式控制动作

它不是推荐的生产任务启动入口。

## 11. Debug 路径：通过 API 创建 Run

为了本地调试和测试，你仍然可以通过后端创建一个 run：

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "title": "Debug run",
    "taskText": "Inspect README.md and write a short report."
  }'
```

这条路径使用的是同一套 core library，但它只是 operator convenience path，不是推荐的 OpenClaw 原生入口。
