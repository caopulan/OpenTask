# Registry 参考

[English Version](./registry.md)

## 真源

只把 registry 当作唯一持久真源。

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

## 每个文件的含义

- `workflow.lock.md`：当前 run 的冻结工作流快照
- `state.json`：给 UI 和操作者使用的状态投影
- `refs.json`：OpenClaw 运行时绑定，例如 source session、root session、cron、child sessions
- `events.jsonl`：追加式审计日志
- `control.jsonl`：显式人工或 UI 动作

## 允许的人工修改

允许：

- 编辑 `workflows/*.task.md`
- 向 `control.jsonl` 追加新记录

不允许：

- 手工改 `state.json`
- 手工改 `refs.json`
- 重写或删除 `events.jsonl`

## 节点输出契约

节点完成后应该留下：

- `nodes/<nodeId>/report.md`，给人看的报告
- `nodes/<nodeId>/result.json`，给机器读的状态和 session 绑定

项目的完整契约见 [../../../docs/registry-spec.ZH.md](../../../docs/registry-spec.ZH.md)。
