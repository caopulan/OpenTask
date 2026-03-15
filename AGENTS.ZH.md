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

## Python 环境
- 使用 `uv` 管理 Python 版本、虚拟环境、依赖和命令。
- 项目的虚拟环境固定放在 `.venv`。
- 推荐工作流：
  - `uv venv --python 3.12 .venv`
  - `uv sync`
  - `uv add <package>`
  - `uv run <command>`
