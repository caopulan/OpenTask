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

对真实 workflow 来说，这里应该是稳定的 OpenClaw workspace，或其他长期存在的共享目录。如果你希望 OpenTask 后端和前端看到同一批 run，就不要依赖一次性的临时目录。

## 4. 校验示例工作流

```bash
uv run opentask workflow validate workflows/research-demo.task.md
```

## 5. 在 OpenClaw 中启动工作流

在你希望任务长期运行的 OpenClaw 对话里：

1. 使用 [skills/opentask/SKILL.ZH.md](skills/opentask/SKILL.ZH.md)
2. 要求 agent 把当前对话当作 root orchestrator session
3. 要求它在写文件前先解析当前 session 和 registry root
4. 要求它在 `workflows/` 下创建或校验工作流
5. 要求它把 run 绑定到当前 session 并开始执行

示例提示词：

```text
对这个对话使用 opentask skill。先解析 registry root 和当前 session，把当前 session 作为 root orchestrator，创建或校验 workflow，把 run 绑定到当前 session，并持续执行直到完成。
```

在实现层，这个 skill 会先把 references 全部读完，解析当前 `sessionKey`、`agentId`、`deliveryContext` 和 registry root，先把 run scaffold 完整，再启动 cron 或派发执行。`workflows/` 下的源 workflow 必须保持可复用，不能塞进 run-local 元数据。CLI 主要给 operator、测试和 UI 集成使用，不是面向最终用户的主入口。

## 6. 查看 Registry

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

对于支持节点级 working memory 的节点目录，你还应该能看到这些规范文件：

- `plan.md`
- `findings.md`
- `progress.md`
- `handoff.md`，用于 subagent 节点

每个文件的约定见 [docs/registry-spec.ZH.md](docs/registry-spec.ZH.md)。

## 7. 直接在 OpenClaw 中控制工作流

继续在同一个 OpenClaw 对话里控制这个 run。常见例子：

- 暂停：
  `等当前活跃节点结束后，把这个 workflow 暂停。`
- 恢复：
  `恢复这个 workflow，按当前计划继续执行。`
- 请求进度更新：
  `在这个对话里给我发一个简短的阶段性进度更新。`
- 修改执行节奏：
  `把 cron 调慢一些，这个任务可以后台跑。`

这个 skill 应该把这些请求翻译成原生 OpenClaw 动作：

- 通过 `control.jsonl` 追加或解释控制意图
- 在需要时更新 workflow 或 run 文件
- 通过 OpenClaw 工具修改 cron
- 保持内部 tick 对用户不可见
- 只在合适的时候发送显式的用户可见消息

## 8. Operator 等价命令

下面这些命令是给 operator、调试、UI 集成和测试使用的，不是最终用户的主控制路径：

```bash
uv run opentask control pause <runId>
uv run opentask control resume <runId>
uv run opentask control send_message <runId> --message "Still running."
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
