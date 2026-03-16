# AGENTS.md

[English](AGENTS.md) | 中文

## 协作约定
- 每完成一个完整的变更切片，就在结束任务前提交一次 git commit，除非用户明确要求不要提交。
- 每次 commit 之后都立即把当前分支 push 到配置好的远程，除非用户明确要求不要 push。
- 所有 commit message 都使用 Conventional Commits：`type(scope): summary`。
- commit subject 使用祈使句，冒号后保持简洁，并统一小写风格。
- 推荐类型：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`build`、`ci`。

## 中间文件
- 不要提交开发过程中的草稿文件、计划笔记、临时调研结果或其他中间文档。
- 像 `task_plan.md`、`findings.md`、`progress.md`、`TaskOrchestrator.md`、`cron_ref.md` 这类文件保持未跟踪状态，除非用户明确要求把它们版本化。

## Skill 测试
- 在验证或调试 skill 时，先创建一个 Codex sub-agent，并隔离它的上下文。
- 不要把父会话上下文、整个仓库上下文或无关文件传给这个 sub-agent；只提供 skill 入口文件，以及 skill 文档明确要求它读取的文件。
- 为测试创建一个临时工作目录，并在该目录中给 sub-agent 指派一个具体任务。
- 这个任务必须要求 sub-agent 真正遵循 skill，例如拆解工作流、写出工作流文件，或按文档协议模拟 sub-agent 调度。
- 要求它在临时目录中产生可观察、可验证的落盘结果，不能只依赖它的文字说明来判断是否执行正确。
- 验证生成的文件、格式和执行步骤是否符合 skill 说明。缺少文件、格式错误或违反协议，都应视为 skill 缺陷，而不只是执行误差。
- 持续迭代 skill，直到一个隔离上下文的 sub-agent 仅凭这份 skill 文档就能按预期完整完成任务。
- 所有临时测试目录和产物都保持未跟踪状态，除非用户明确要求保留并提交。
- 在这台机器上做本地 OpenClaw 验证时，`main` agent 继承的 workspace 是 `/Users/chunqiu/clawd`。
- `main` 的 workspace skill 安装根目录是 `/Users/chunqiu/clawd/skills`。
- 如果用软链接安装 skill，软链接最终解析后的目标也必须落在 `/Users/chunqiu/clawd/skills` 下面；OpenClaw 会拒绝加载解析后逃逸出这个根目录的 workspace skill。

## Python 环境
- 使用 `uv` 管理 Python 版本、虚拟环境、依赖和命令。
- 项目的虚拟环境固定放在 `.venv`。
- 推荐工作流：
  - `uv venv --python 3.12 .venv`
  - `uv sync`
  - `uv add <package>`
  - `uv run <command>`
