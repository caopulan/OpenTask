# AGENTS.md

English | [中文](AGENTS.ZH.md)

## Working Agreement
- Complete each coherent change set with a git commit before ending the task, unless the user explicitly says not to commit.
- After each commit, immediately push the current branch to the configured remote unless the user explicitly says not to push.
- Use Conventional Commits for every commit message: `type(scope): summary`.
- Keep commit subjects imperative, concise, and lowercase after the colon.
- Preferred types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`.

## Intermediate Files
- Do not commit development scratch files, planning notes, temporary research, or other intermediate documents.
- Keep files such as `task_plan.md`, `findings.md`, `progress.md`, `TaskOrchestrator.md`, and `cron_ref.md` untracked unless the user explicitly asks for them to be versioned.

## Skill Testing
- When validating or debugging a skill, create a Codex sub-agent and isolate its context.
- Do not pass the parent conversation context, repository-wide context, or unrelated files into that sub-agent; only provide the skill entrypoint and the specific files that the skill itself tells the agent to read.
- Create a temporary working directory for the test and assign the sub-agent a concrete task inside that directory.
- The task must require the sub-agent to follow the skill: for example, decompose a workflow, write workflow files, or simulate sub-agent dispatch according to the documented protocol.
- Require observable file outputs in the temporary directory so the result can be verified without relying on the sub-agent's narration alone.
- Verify that the generated files, formats, and execution steps match the skill instructions. Treat missing files, wrong formats, or protocol violations as a skill bug, not just an execution mistake.
- Iterate on the skill until an isolated sub-agent can complete the task exactly as intended using only the skill documentation.
- Keep all temporary test directories and artifacts untracked unless the user explicitly asks to preserve them.
- For local OpenClaw validation on this machine, the `main` agent inherits workspace `/Users/chunqiu/clawd`.
- Workspace-installed skills for `main` live under `/Users/chunqiu/clawd/skills`.
- If a skill is installed via symlink, the symlink target must also resolve under `/Users/chunqiu/clawd/skills`; OpenClaw rejects workspace skills whose resolved path escapes that root.

## Python Environment
- Use `uv` for Python version, virtual environment, dependency, and command management.
- The project virtual environment lives at `.venv`.
- Preferred workflow:
  - `uv venv --python 3.12 .venv`
  - `uv sync`
  - `uv add <package>`
  - `uv run <command>`
