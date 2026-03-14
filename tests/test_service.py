from __future__ import annotations

from pathlib import Path

import pytest

from opentask.models import CreateRunRequest
from opentask.service import OpenTaskService
from opentask.store import RunStore


class FakeGateway:
    def __init__(self) -> None:
        self.cron_enabled = True
        self.sent_messages: list[dict] = []
        self.wait_results: dict[str, dict] = {}

    async def send_chat(self, **kwargs):
        self.sent_messages.append(kwargs)
        run_id = kwargs["idempotency_key"]
        status = "started"
        if "summary" in kwargs["session_key"]:
            status = "ok"
        self.wait_results.setdefault(run_id, {"status": "ok", "runId": run_id})
        return {"status": status, "runId": run_id}

    async def wait_run(self, run_id: str, timeout_ms: int):
        return self.wait_results.get(run_id, {"status": "timeout", "runId": run_id})

    async def cron_add(self, params: dict):
        return {"jobId": f"cron-{params['name'].split()[-1]}"}

    async def cron_update(self, job_id: str, patch: dict):
        self.cron_enabled = patch.get("enabled", True)
        return {"jobId": job_id, "patch": patch}

    async def cron_run(self, job_id: str):
        return {"jobId": job_id, "status": "ok"}

    async def chat_history(self, session_key: str, limit: int = 20):
        return []


@pytest.mark.asyncio
async def test_create_run_bootstraps_cron_and_summary(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Complete the task", title="Demo"))

    assert state.cron_job_id is not None
    assert state.status == "running"
    assert any(node.kind == "summary" for node in state.nodes)
    assert any(msg["session_key"].endswith(":planner") for msg in gateway.sent_messages)


@pytest.mark.asyncio
async def test_approval_gate_can_be_approved(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)
    markdown = """---
workflowId: approval-demo
title: Approval demo
nodes:
  - id: gather
    title: Gather
    kind: session_turn
    needs: []
    prompt: Gather things
    outputs:
      mode: report
  - id: gate
    title: Gate
    kind: approval
    needs: [gather]
    prompt: Wait
    outputs:
      mode: notify
  - id: finish
    title: Finish
    kind: summary
    needs: [gate]
    prompt: Finish
    outputs:
      mode: report
---
"""
    state = await service.create_run(CreateRunRequest(workflowMarkdown=markdown))
    state = await service.tick_run(state.run_id)
    gate = next(node for node in state.nodes if node.id == "gate")
    assert gate.status == "waiting"

    state = await service.approve_node(state.run_id, "gate")
    gate = next(node for node in state.nodes if node.id == "gate")
    finish = next(node for node in state.nodes if node.id == "finish")
    assert gate.status == "completed"
    assert finish.status in {"completed", "ready", "running"}


@pytest.mark.asyncio
async def test_pause_and_resume_updates_status(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Pause me", title="Pause demo"))
    paused = await service.pause_run(state.run_id)
    resumed = await service.resume_run(state.run_id)

    assert paused.status == "paused"
    assert resumed.status == "running"


@pytest.mark.asyncio
async def test_wait_node_advances_when_file_appears(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)
    markdown = """---
workflowId: wait-file-demo
title: Wait for file
nodes:
  - id: gather
    title: Gather
    kind: session_turn
    needs: []
    prompt: Gather context
    outputs:
      mode: report
  - id: wait-for-signal
    title: Wait for signal
    kind: wait
    needs: [gather]
    waitFor:
      type: file_exists
      path: signals/ready.flag
    outputs:
      mode: notify
  - id: finish
    title: Finish
    kind: summary
    needs: [wait-for-signal]
    prompt: Summarize
    outputs:
      mode: report
---
"""
    state = await service.create_run(CreateRunRequest(workflowMarkdown=markdown))
    state = await service.tick_run(state.run_id)
    waiting = next(node for node in state.nodes if node.id == "wait-for-signal")
    assert waiting.status == "waiting"

    service.store.write_support_file(state.run_id, "signals/ready.flag", "ready\n")
    state = await service.tick_run(state.run_id)

    waiting = next(node for node in state.nodes if node.id == "wait-for-signal")
    finish = next(node for node in state.nodes if node.id == "finish")
    assert waiting.status == "completed"
    assert finish.status == "completed"
    assert state.status == "completed"


@pytest.mark.asyncio
async def test_run_can_resume_from_runtime_store_after_restart(tmp_path: Path) -> None:
    gateway = FakeGateway()
    runtime_root = tmp_path / ".opentask"
    service = OpenTaskService(store=RunStore(runtime_root=runtime_root), gateway=gateway)

    created = await service.create_run(CreateRunRequest(taskText="Recover after restart", title="Recovery demo"))

    restarted = OpenTaskService(store=RunStore(runtime_root=runtime_root), gateway=gateway)
    listed = restarted.list_runs()
    assert len(listed) == 1
    assert listed[0].run_id == created.run_id

    recovered = await restarted.tick_run(created.run_id)
    assert recovered.run_id == created.run_id
    assert recovered.status == "completed"
