# OpenTask

[English Version](./SKILL.md)

把 OpenClaw 视为执行平面，把 OpenTask 视为 registry 和控制平面。

## 按这个流程执行

1. 用 `sessions_list` 解析当前 session。
2. 记录 `sessionKey`、`agentId` 和 `deliveryContext`。
3. 创建或更新 `workflows/*.task.md`。
4. 用 `uv run opentask workflow validate ...` 校验工作流。
5. 把当前 session 作为 root orchestrator，创建或绑定 run。
6. 让 OpenClaw 通过 root session、subagent 和 cron 持续推进。
7. 需要人工介入时，追加显式 control。

## 按需读取这些参考

- 需要命令、session 绑定或控制动作时，读 [references/operations.ZH.md](./references/operations.ZH.md)。
- 需要 registry 目录、允许修改的文件或节点输出格式时，读 [references/registry.ZH.md](./references/registry.ZH.md)。

## 保持这些规则

- 把当前面向用户的 session 当作 root orchestrator session。
- 用户可见进度必须通过显式更新发送，不要暴露原始 orchestration prompt。
- 让 OpenClaw 执行节点和 cron，让 OpenTask 记录 registry 状态和 control。
- 允许编辑 workflow 文件或追加 control，不要手工修改 `state.json`、`refs.json`、`events.jsonl`。
- 节点输出统一写成 `report.md` 和 `result.json`。
