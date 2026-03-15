# OpenTask Web

[English](README.md) | 中文

前端是一个基于 React Flow 的 OpenTask 控制平面，用来展示 registry 中的 run 列表、DAG、事件时间线、source session 绑定，以及 `pause`、`resume`、`retry`、`skip`、`approve`、`send message`、`patch cron`、`force tick` 等显式操作入口。

如果你想按完整流程启动整个项目，先看 [../QUICKSTART.ZH.md](../QUICKSTART.ZH.md)。

## 命令

```bash
pnpm install
pnpm dev
pnpm lint
pnpm build
```

Vite 开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`。如果前端要单独部署，请在运行或构建前设置 `VITE_API_BASE`。
