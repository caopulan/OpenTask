# AGENTS.md

English | [中文](AGENTS.ZH.md)

## Working Agreement
- Complete each coherent change set with a git commit before ending the task, unless the user explicitly says not to commit.
- Use Conventional Commits for every commit message: `type(scope): summary`.
- Keep commit subjects imperative, concise, and lowercase after the colon.
- Preferred types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`.

## Intermediate Files
- Do not commit development scratch files, planning notes, temporary research, or other intermediate documents.
- Keep files such as `task_plan.md`, `findings.md`, `progress.md`, `TaskOrchestrator.md`, and `cron_ref.md` untracked unless the user explicitly asks for them to be versioned.

## Python Environment
- Use `uv` for Python version, virtual environment, dependency, and command management.
- The project virtual environment lives at `.venv`.
- Preferred workflow:
  - `uv venv --python 3.12 .venv`
  - `uv sync`
  - `uv add <package>`
  - `uv run <command>`
