from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from opentask.models import CreateRunRequest
from opentask.openclaw_client import OpenClawGatewayError
from opentask.service import OpenTaskService
from opentask.store import RunStore
from opentask.workflow import build_starter_workflow


class FakeGateway:
    def __init__(self) -> None:
        self.cron_enabled = True
        self.sent_messages: list[dict] = []
        self.spawned_sessions: list[dict] = []
        self.wait_results: dict[str, dict] = {}
        self.session_histories: dict[str, list[dict]] = {}

    async def send_chat(self, **kwargs):
        self.sent_messages.append(kwargs)
        run_id = kwargs["idempotency_key"]
        status = "started"
        if "summary" in kwargs["session_key"]:
            status = "ok"
        self.wait_results.setdefault(run_id, {"status": "ok", "runId": run_id})
        return {"status": status, "runId": run_id}

    async def spawn_session(self, **kwargs):
        self.spawned_sessions.append(kwargs)
        run_id = f"spawn-{len(self.spawned_sessions)}"
        child_session_key = f"agent:main:subagent:{len(self.spawned_sessions)}"
        self.wait_results.setdefault(
            run_id,
            {"status": "ok", "runId": run_id, "childSessionKey": child_session_key},
        )
        return {"status": "accepted", "runId": run_id, "childSessionKey": child_session_key}

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
        return self.session_histories.get(session_key, [])[-limit:]


class SlowGateway(FakeGateway):
    async def send_chat(self, **kwargs):
        await asyncio.sleep(0.05)
        return await super().send_chat(**kwargs)


class FlakyHistoryGateway(FakeGateway):
    async def chat_history(self, session_key: str, limit: int = 20):
        raise OpenClawGatewayError("transport_error", "gateway transport failed during chat.history")


@pytest.mark.asyncio
async def test_create_run_bootstraps_cron_and_summary(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Complete the task", title="Demo"))

    assert state.cron_job_id is not None
    assert state.status == "running"
    assert any(node.kind == "summary" for node in state.nodes)
    assert state.driver_session_key.startswith("agent:opentask:session:workflow:")
    assert any(msg["session_key"].startswith("agent:opentask:session:workflow:") for msg in gateway.sent_messages)
    execute_prompt = next(
        msg["message"]
        for msg in gateway.sent_messages
        if msg["session_key"].endswith(":node:execute-task")
    )
    assert ".opentask/runs/" in execute_prompt
    assert "Preferred artifact paths:" in execute_prompt


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
async def test_subagent_nodes_use_sessions_spawn(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)
    markdown = """---
workflowId: subagent-demo
title: Subagent demo
defaults:
  agentId: main
nodes:
  - id: delegate
    title: Delegate
    kind: subagent
    needs: []
    prompt: Implement the delegated task
    outputs:
      mode: report
  - id: finish
    title: Finish
    kind: summary
    needs: [delegate]
    prompt: Done
    outputs:
      mode: report
---
"""

    state = await service.create_run(CreateRunRequest(workflowMarkdown=markdown))
    delegate = next(node for node in state.nodes if node.id == "delegate")
    assert delegate.status == "running"
    assert delegate.child_session_key == "agent:main:subagent:1"
    assert "Implement the delegated task" in gateway.spawned_sessions[0]["task"]
    assert ".opentask/runs/" in gateway.spawned_sessions[0]["task"]
    assert gateway.spawned_sessions[0]["cwd"] == str(service.project_root)
    assert not any(
        msg["session_key"].endswith(":node:delegate") and msg["message"] == "Implement the delegated task"
        for msg in gateway.sent_messages
    )

    state = await service.tick_run(state.run_id)
    delegate = next(node for node in state.nodes if node.id == "delegate")
    finish = next(node for node in state.nodes if node.id == "finish")
    assert delegate.status == "completed"
    assert finish.status == "completed"
    assert state.status == "completed"


@pytest.mark.asyncio
async def test_custom_agent_id_scopes_run_sessions(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)
    markdown = """---
workflowId: custom-agent-demo
title: Custom agent demo
defaults:
  agentId: ops
nodes:
  - id: gather
    title: Gather
    kind: session_turn
    needs: []
    prompt: Gather context
    outputs:
      mode: report
---
"""

    state = await service.create_run(CreateRunRequest(workflowMarkdown=markdown))

    assert state.driver_session_key.startswith("agent:ops:session:workflow:")
    assert any(msg["session_key"].startswith("agent:ops:session:workflow:") for msg in gateway.sent_messages)


@pytest.mark.asyncio
async def test_existing_node_report_is_not_overwritten_on_completion(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Preserve report", title="Preserve report"))
    report_path = tmp_path / ".opentask" / "runs" / state.run_id / "nodes" / "execute-task" / "report.md"
    report_path.write_text("# Real report\n\nKeep this content.\n", encoding="utf-8")

    state = await service.tick_run(state.run_id)
    execute = next(node for node in state.nodes if node.id == "execute-task")

    assert execute.status == "completed"
    assert report_path.read_text(encoding="utf-8") == "# Real report\n\nKeep this content.\n"


@pytest.mark.asyncio
async def test_summary_artifact_path_is_not_duplicated(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Summarize once", title="Summary dedupe"))
    state = await service.tick_run(state.run_id)
    summary = next(node for node in state.nodes if node.id == "summary")

    assert summary.status == "completed"
    assert summary.artifact_paths == ["nodes/summary/report.md"]


@pytest.mark.asyncio
async def test_driver_directive_can_add_and_rewire_nodes(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Draft an implementation plan", title="Driver mutate"))
    gateway.session_histories[state.driver_session_key] = [
        {
            "role": "assistant",
            "content": (
                "<opentask-mutation>"
                '{"id":"drv-1","summary":"add review stage","mutations":['
                '{"kind":"add_node","node":{"id":"review","title":"Review draft","kind":"session_turn",'
                '"needs":["execute-task"],"prompt":"Review the draft output","outputs":{"mode":"report"}}},'
                '{"kind":"rewire_node","nodeId":"summary","needs":["review"]}'
                "]}"
                "</opentask-mutation>"
            ),
        }
    ]

    state = await service.tick_run(state.run_id)

    review = next(node for node in state.nodes if node.id == "review")
    summary = next(node for node in state.nodes if node.id == "summary")
    execute = next(node for node in state.nodes if node.id == "execute-task")
    assert execute.status == "completed"
    assert review.status == "running"
    assert summary.status == "pending"
    assert summary.needs == ["review"]

    workflow = service.store.load_workflow_lock(state.run_id)
    assert [node.id for node in workflow.definition.nodes][-2:] == ["review", "summary"]
    events = service.get_events(state.run_id)
    assert any(event.event == "node.added" and event.node_id == "review" for event in events)
    assert any(event.event == "node.rewired" and event.node_id == "summary" for event in events)
    assert any(event.event == "driver.directive.applied" for event in events)

    state = await service.tick_run(state.run_id)
    assert [node.id for node in state.nodes].count("review") == 1
    assert any("Review the draft output" in item["message"] for item in gateway.sent_messages)


@pytest.mark.asyncio
async def test_tick_requests_driver_turn_when_run_changes(tmp_path: Path) -> None:
    gateway = FakeGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Prepare a plan", title="Driver auto prompt"))

    driver_messages = [
        message for message in gateway.sent_messages if message["session_key"] == state.driver_session_key
    ]
    assert driver_messages
    assert "Current nodes:" in driver_messages[-1]["message"]
    assert "If you want no graph changes, reply exactly NO_CHANGE." in driver_messages[-1]["message"]

    refs = service.store.load_openclaw_refs(state.run_id)
    assert refs.driver_run_id is not None
    assert refs.driver_requested_event_count >= 1
    assert (service.store.runs_root / state.run_id / "driver.context.md").exists()


@pytest.mark.asyncio
async def test_concurrent_ticks_do_not_duplicate_dispatch(tmp_path: Path) -> None:
    gateway = SlowGateway()
    store = RunStore(runtime_root=tmp_path / ".opentask")
    service = OpenTaskService(store=store, gateway=gateway)
    workflow = build_starter_workflow("Concurrent tick", "Run only once")
    state, _ = store.create_run(workflow)

    await asyncio.gather(service.tick_run(state.run_id), service.tick_run(state.run_id))

    execute_messages = [
        message
        for message in gateway.sent_messages
        if message["session_key"].endswith(":node:execute-task")
    ]
    assert len(execute_messages) == 1

    events = service.get_events(state.run_id)
    execute_started = [event for event in events if event.event == "node.started" and event.node_id == "execute-task"]
    assert len(execute_started) == 1


@pytest.mark.asyncio
async def test_driver_history_failure_does_not_abort_tick(tmp_path: Path) -> None:
    gateway = FlakyHistoryGateway()
    service = OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway)

    state = await service.create_run(CreateRunRequest(taskText="Handle flaky history", title="Flaky history"))
    state = await service.tick_run(state.run_id)

    assert state.run_id.startswith("opentask-")
    assert any(event.event == "driver.history.unavailable" for event in service.get_events(state.run_id))


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
