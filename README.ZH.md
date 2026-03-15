# OpenTask

<p align="center">
  <img src="web/src/assets/hero.png" alt="OpenTask" width="220">
</p>

<p align="center">面向长时间运行 OpenClaw Session 的文件化工作流编排器。</p>

<p align="center">
  <a href="README.md">English</a> ·
  中文 ·
  <a href="QUICKSTART.ZH.md">快速上手教程</a>
</p>

<p align="center">
  <a href="#安装">安装</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="QUICKSTART.ZH.md">教程</a> •
  <a href="#工作流格式">工作流格式</a> •
  <a href="#api">API</a> •
  <a href="#文档">文档</a> •
  <a href="#当前限制">当前限制</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI backend">
  <img src="https://img.shields.io/badge/runtime-OpenClaw-111111" alt="OpenClaw runtime">
  <img src="https://img.shields.io/badge/status-experimental-orange" alt="Experimental status">
</p>

OpenTask 是一个构建在 OpenClaw 之上的 Web 应用与运行时，用来规划、执行并审计 Agent 工作流。它把工作流 DAG、运行态投影和追加式事件日志落到本地磁盘，同时把 session、child session、cron 驱动回合这些执行事实交给 OpenClaw 维护。

它面向需要“可检查、可留档、可长期运行”的 Agent 工作流的开发者和操作者，而不是一次性 prompt。你既可以从自由文本任务启动，也可以从版本化的 Markdown 工作流启动，在网页里观察图结构演化，并持续推进运行直到所有节点进入终态。

如果你想先按步骤实操一次，直接看 [QUICKSTART.ZH.md](QUICKSTART.ZH.md)。

## 特性 ✨

- 使用 Markdown + YAML frontmatter 定义工作流
- 基于文件系统的运行态目录 `.opentask/runs/<runId>/`
- 真实接入 OpenClaw 的 planner、driver、node 与 subagent session
- 支持 driver directive 在线增删改工作流结构
- 提供 run 列表、DAG 视图、时间线和节点控制的 Web UI
- 提供跨进程 run 协调，避免重复派发
- 用 `workflow.lock.md`、`state.json`、`events.jsonl` 与 `openclaw.json` 保留可恢复审计轨迹

## 工作方式 ⚙️

OpenTask 和 OpenClaw 的职责边界如下：

| 层 | OpenTask 负责 | OpenClaw 负责 |
| --- | --- | --- |
| 工作流模型 | DAG 定义、workflow lock、节点依赖 | 无 |
| 运行态 | `state.json`、`events.jsonl`、节点产物 | 无 |
| 执行 | 派发策略、driver directive 应用、人工控制动作 | Sessions、child sessions、cron jobs、run 完成事实 |
| UI | run 列表、图视图、时间线、控制面板 | 无 |

这个分层让你既能把人类可读的审计轨迹保存在磁盘里，又能继续复用 OpenClaw 的 session 和 cron 机制。

## 安装

### 前置条件

- Python 3.12+
- `uv`
- Node.js 与 `pnpm`
- 一个正在运行的 OpenClaw Gateway
- 一个指向当前仓库的 OpenClaw agent workspace

### 安装后端与前端依赖

```bash
uv sync --dev
pnpm --dir web install
```

### 配置 OpenClaw workspace

默认情况下，OpenTask 会把运行绑定到 OpenClaw 的 `opentask` agent。请把这个 agent 的 workspace 指向当前仓库，或者用 `OPENTASK_AGENT_ID` 覆盖。

OpenTask 会自动复用本机已有的 device auth 文件：

- `~/.openclaw/identity/device.json`
- `~/.openclaw/identity/device-auth.json`

如有需要，也可以显式覆盖：

```bash
export OPENTASK_GATEWAY_URL=ws://127.0.0.1:18789
export OPENTASK_AGENT_ID=opentask
export OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH=/path/to/device.json
export OPENTASK_GATEWAY_DEVICE_AUTH_PATH=/path/to/device-auth.json
```

## 快速开始

完整教程见 [QUICKSTART.ZH.md](QUICKSTART.ZH.md)。这里保留最短路径：

### 1. 安装依赖

```bash
uv sync --dev
pnpm --dir web install
```

### 2. 启动后端

```bash
uv run opentask-api
```

API 默认监听 `http://127.0.0.1:8000`。

### 3. 启动 Web UI

```bash
pnpm --dir web dev
```

Vite 默认监听 `http://127.0.0.1:5174/`，并把 `/api` 与 WebSocket 请求代理到后端。

### 4. 用自由文本创建一个 run

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "title": "First run",
    "taskText": "Review AGENTS.md and write a short report about repo conventions."
  }'
```

示例返回：

```json
{
  "runId": "opentask-1234abcd",
  "status": "running",
  "workflowId": "first-run"
}
```

### 5. 查看 run 和事件

```bash
curl http://127.0.0.1:8000/api/runs
curl http://127.0.0.1:8000/api/runs/opentask-1234abcd/events
```

### 6. 用工作流文件启动 run

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "workflowPath": "workflows/research-demo.task.md"
  }'
```

## 工作流格式

版本化工作流放在 `workflows/*.task.md`，由 Markdown 正文和 YAML frontmatter 组成。

最小示例：

```md
---
workflowId: quick-demo
title: Quick demo
defaults:
  agentId: opentask
nodes:
  - id: execute-task
    title: Execute task
    kind: session_turn
    needs: []
    prompt: Write a short report.
    outputs:
      mode: report
      requiredFiles:
        - nodes/execute-task/report.md
  - id: summary
    title: Summary
    kind: summary
    needs:
      - execute-task
    prompt: Summarize the run.
    outputs:
      mode: report
      requiredFiles:
        - nodes/summary/report.md
---
```

支持的节点类型：

- `session_turn`
- `subagent`
- `wait`
- `approval`
- `summary`

支持的输出模式：

- `notify`
- `report`

driver session 还可以输出结构化 mutation block，在 run 运行过程中新增节点或重连依赖。

完整样例见 [workflows/research-demo.task.md](workflows/research-demo.task.md)。

## 运行时目录 🗂️

每个 run 都在 `.opentask/runs/<runId>/` 下保存：

| 路径 | 作用 |
| --- | --- |
| `workflow.lock.md` | 当前 run 的冻结工作流快照 |
| `state.json` | API 和 UI 直接读取的状态投影 |
| `events.jsonl` | 追加式审计日志 |
| `openclaw.json` | planner、driver、cron 和 node session 映射 |
| `driver.context.md` | 最近一次 driver review 的 prompt 快照 |
| `nodes/<nodeId>/` | 节点报告与其他节点级产物 |
| `.run.lock` | 当前 run 的跨进程协调锁 |

运行态目录默认被 git 忽略。

## API

当前提供的接口：

- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/events`
- `POST /api/runs/{runId}/actions/{pause|resume|retry|skip|approve|tick}`
- `WS /api/runs/{runId}/stream`

一个人工控制动作示例：

```bash
curl -X POST http://127.0.0.1:8000/api/runs/opentask-1234abcd/actions/tick \
  -H 'content-type: application/json' \
  -d '{}'
```

## 配置 🔧

常用环境变量：

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `OPENTASK_GATEWAY_URL` | `ws://127.0.0.1:18789` | OpenClaw Gateway 地址 |
| `OPENTASK_AGENT_ID` | `opentask` | 持有 run session 的 agent/workspace |
| `OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH` | `~/.openclaw/identity/device.json` | 设备身份文件 |
| `OPENTASK_GATEWAY_DEVICE_AUTH_PATH` | `~/.openclaw/identity/device-auth.json` | 设备授权 token 存储 |

## 文档

推荐按下面顺序阅读：

- [README.md](README.md) 查看英文默认说明
- [README.ZH.md](README.ZH.md) 查看中文总览
- [QUICKSTART.md](QUICKSTART.md) 查看英文上手教程
- [QUICKSTART.ZH.md](QUICKSTART.ZH.md) 查看中文上手教程
- [AGENTS.md](AGENTS.md) 查看仓库协作规则
- [AGENTS.ZH.md](AGENTS.ZH.md) 查看中文协作规则
- [workflows/research-demo.task.md](workflows/research-demo.task.md) 查看完整 workflow 示例
- [workflows/research-demo.task.ZH.md](workflows/research-demo.task.ZH.md) 查看中文 workflow 示例
- [web/README.md](web/README.md) 查看前端说明
- [web/README.ZH.md](web/README.ZH.md) 查看中文前端说明
- [tests/test_service.py](tests/test_service.py) 查看编排行为和回归覆盖

## 当前限制

OpenTask 已经可用，但还不是完全产品化的基础设施。

- 依赖一个正在运行的 OpenClaw Gateway 和已配置好的本地 agent workspace。
- 运行态存储仍是本地文件系统，不是分布式存储。
- 暂时没有图形化 DAG 编辑器，UI 只负责查看和控制。
- 当前项目还没有发布正式安装包或安装器。

## 贡献 🤝

欢迎提 issue 和 pull request。较大的改动建议先开 issue，对齐工作流和存储模型后再实现。

## 许可证

仓库目前还没有发布许可证文件。在添加正式许可证之前，请按保留所有权处理。
