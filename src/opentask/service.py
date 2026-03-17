from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .config import get_settings
from .driver_protocol import driver_mutation_instructions, extract_driver_directives
from .models import (
    CreateRunRequest,
    NodeResult,
    NodeState,
    RunActionRequest,
    RunControlAction,
    RunEvent,
    RunNodeDocument,
    RunRefs,
    RunState,
    WorkflowDefinition,
    utc_now,
)
from .openclaw_client import OpenClawClient, OpenClawGatewayError
from .run_lock import RunFileLock
from .session_keys import qualify_agent_session_key
from .store import RunStore
from .transcript import extract_last_assistant_final_text
from .workflow import (
    build_starter_workflow,
    ensure_summary_node,
    ensure_relative_paths,
    load_workflow,
    normalize_artifact_paths,
    parse_workflow_markdown,
    validate_workflow_definition,
)


class GatewayProtocol(Protocol):
    async def send_chat(
        self,
        *,
        session_key: str,
        message: str,
        idempotency_key: str,
        timeout_ms: int,
        thinking: str | None = None,
        deliver: bool = False,
    ) -> dict: ...

    async def spawn_session(
        self,
        *,
        parent_session_key: str,
        task: str,
        label: str | None = None,
        agent_id: str | None = None,
        model: str | None = None,
        thinking: str | None = None,
        cwd: str | None = None,
        timeout_seconds: int | None = None,
        mode: str = "run",
        cleanup: str = "keep",
        sandbox: str = "inherit",
    ) -> dict: ...

    async def wait_run(self, run_id: str, timeout_ms: int) -> dict: ...

    async def cron_add(self, params: dict) -> dict: ...

    async def cron_update(self, job_id: str, patch: dict) -> dict: ...

    async def cron_run(self, job_id: str) -> dict: ...

    async def chat_history(self, session_key: str, limit: int = 20) -> list[dict]: ...

    async def send_outbound_message(
        self,
        *,
        session_key: str,
        channel: str,
        to: str,
        message: str,
        account_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict: ...


TERMINAL_STATUSES = {"completed", "failed", "skipped"}
DRIVER_BOOKKEEPING_EVENTS = {
    "driver.requested",
    "driver.completed",
    "driver.failed",
    "driver.request.failed",
    "driver.status.unavailable",
    "driver.history.unavailable",
    "driver.directive.applied",
    "driver.directive.rejected",
}
PROGRESS_EVENTS = {
    "plan.generated",
    "node.started",
    "node.completed",
    "node.failed",
    "node.waiting",
    "node.skipped",
    "node.added",
    "node.rewired",
    "run.paused",
    "run.resumed",
    "run.completed",
    "cron.patched",
}


class OpenTaskService:
    def __init__(
        self,
        *,
        store: RunStore | None = None,
        gateway: GatewayProtocol | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.settings = get_settings()
        self.project_root = project_root or self.settings.project_root
        self.store = store or RunStore()
        self.execution_root = self.store.registry_root
        self.gateway = gateway or OpenClawClient()
        self.run_file_lock = RunFileLock(self.store.runtime_root)
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = defaultdict(set)
        self._run_locks: dict[str, asyncio.Lock] = {}

    def list_runs(self) -> list[RunState]:
        return self.store.list_runs()

    def get_run(self, run_id: str) -> RunState:
        return self.store.load_state(run_id)

    def get_events(self, run_id: str, limit: int | None = None) -> list[RunEvent]:
        return self.store.load_events(run_id, limit=limit)

    def get_node_documents(self, run_id: str, node_id: str) -> list[RunNodeDocument]:
        return self.store.load_node_documents(run_id, node_id)

    async def bind_run(
        self,
        run_id: str,
        *,
        source_session_key: str | None = None,
        source_agent_id: str | None = None,
        delivery_context=None,
        root_session_key: str | None = None,
    ) -> RunState:
        async with self._run_scope(run_id):
            state = self.store.load_state(run_id)
            refs = self.store.load_run_refs(run_id)
            resolved_root_session_key = root_session_key or source_session_key or state.root_session_key
            state = self.store.update_state_timestamp(
                state.model_copy(
                    update={
                        "source_session_key": source_session_key or state.source_session_key,
                        "source_agent_id": source_agent_id or state.source_agent_id,
                        "delivery_context": delivery_context or state.delivery_context,
                        "root_session_key": resolved_root_session_key,
                        "planner_session_key": resolved_root_session_key,
                        "driver_session_key": resolved_root_session_key,
                    }
                ),
                last_event="run.bound",
            )
            refs = refs.model_copy(
                update={
                    "source_session_key": source_session_key or refs.source_session_key,
                    "source_agent_id": source_agent_id or refs.source_agent_id,
                    "delivery_context": delivery_context or refs.delivery_context,
                    "root_session_key": resolved_root_session_key,
                    "planner_session_key": resolved_root_session_key,
                    "driver_session_key": resolved_root_session_key,
                }
            )
            self.store.write_state(state)
            self.store.write_run_refs(run_id, refs)
            self.store.append_event(
                run_id,
                RunEvent(
                    event="run.bound",
                    runId=run_id,
                    message="Bound run to a root/source session.",
                    payload={
                        "sourceSessionKey": state.source_session_key,
                        "rootSessionKey": state.root_session_key,
                    },
                ),
            )
            await self._publish(state)
            return state

    async def create_run(self, request: CreateRunRequest) -> RunState:
        parsed = self._resolve_workflow(request)
        parsed, added_events = ensure_summary_node(parsed)
        run_id = self.store.next_run_id()
        async with self._run_scope(run_id):
            state, refs = self.store.create_run(
                parsed,
                run_id=run_id,
                source_session_key=request.source_session_key,
                source_agent_id=request.source_agent_id,
                delivery_context=request.delivery_context,
                root_session_key=request.root_session_key,
            )
            for event in added_events:
                self.store.append_event(
                    state.run_id,
                    event.model_copy(update={"run_id": state.run_id, "timestamp": state.created_at}),
                )

            planner_prompt = self._build_planner_prompt(state.run_id, parsed.body)
            driver_prompt = self._build_driver_prompt(state.run_id)
            self.store.write_support_file(state.run_id, "planner.prompt.md", planner_prompt)
            self.store.write_support_file(state.run_id, "driver.prompt.md", driver_prompt)

            state = await self._bootstrap_openclaw(state, refs, parsed, planner_prompt, driver_prompt)
            state = await self._tick_run_unlocked(state.run_id)
        return state

    async def tick_run(self, run_id: str) -> RunState:
        async with self._run_scope(run_id):
            return await self._tick_run_unlocked(run_id)

    async def _tick_run_unlocked(self, run_id: str) -> RunState:
        workflow = self.store.load_workflow_lock(run_id)
        state = self.store.load_state(run_id)
        refs = self.store.load_run_refs(run_id)
        state, refs = self._normalize_session_keys(state, refs, workflow.definition)
        state, refs = await self._apply_control_actions(state, refs)

        if state.status in {"paused", "completed", "cancelled"}:
            self.store.write_run_refs(run_id, refs)
            self.store.write_state(state)
            return state

        state = await self._sync_running_nodes(state)
        refs = await self._sync_driver_run(state.run_id, refs)
        state = self._advance_waiting_nodes(state)
        state, workflow = await self._apply_driver_directives(state, workflow)
        state = self._promote_ready_nodes(state)
        state = await self._dispatch_ready_nodes(state, workflow.definition, refs)
        refs = await self._maybe_request_driver_turn(state, workflow, refs)
        state = await self._finalize_if_terminal(state)
        state, refs = await self._maybe_emit_progress_update(state, refs)
        self.store.write_run_refs(state.run_id, refs)
        self.store.write_state(state)
        await self._publish(state)
        return state

    async def pause_run(self, run_id: str) -> RunState:
        return await self._enqueue_control_and_tick(
            run_id,
            RunActionRequest(),
            action="pause",
        )

    async def resume_run(self, run_id: str) -> RunState:
        return await self._enqueue_control_and_tick(
            run_id,
            RunActionRequest(),
            action="resume",
        )

    async def retry_node(self, run_id: str, node_id: str) -> RunState:
        return await self._enqueue_control_and_tick(
            run_id,
            RunActionRequest(nodeId=node_id),
            action="retry",
        )

    async def skip_node(self, run_id: str, node_id: str) -> RunState:
        return await self._enqueue_control_and_tick(
            run_id,
            RunActionRequest(nodeId=node_id),
            action="skip",
        )

    async def approve_node(self, run_id: str, node_id: str) -> RunState:
        return await self._enqueue_control_and_tick(
            run_id,
            RunActionRequest(nodeId=node_id),
            action="approve",
        )

    async def force_tick(self, run_id: str) -> RunState:
        async with self._run_scope(run_id):
            refs = self.store.load_run_refs(run_id)
            if refs.cron_job_id:
                await self.gateway.cron_run(refs.cron_job_id)
            return await self._tick_run_unlocked(run_id)

    async def send_message(self, run_id: str, message: str) -> RunState:
        return await self._enqueue_control_and_tick(
            run_id,
            RunActionRequest(message=message),
            action="send_message",
        )

    async def patch_cron(self, run_id: str, patch: dict) -> RunState:
        return await self._enqueue_control_and_tick(
            run_id,
            RunActionRequest(patch=patch),
            action="patch_cron",
        )

    async def _enqueue_control_and_tick(
        self,
        run_id: str,
        request: RunActionRequest,
        *,
        action: str,
    ) -> RunState:
        async with self._run_scope(run_id):
            control = RunControlAction(
                id=f"{run_id}-{action}-{uuid4().hex[:10]}",
                action=action,
                runId=run_id,
                nodeId=request.node_id,
                message=request.message,
                patch=request.patch,
            )
            self.store.append_control_action(run_id, control)
            return await self._tick_run_unlocked(run_id)

    def subscribe(self, run_id: str) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[dict]) -> None:
        self._subscribers[run_id].discard(queue)

    def _resolve_workflow(self, request: CreateRunRequest):
        if request.workflow_markdown:
            return parse_workflow_markdown(request.workflow_markdown)
        if request.workflow_path:
            candidate = Path(request.workflow_path)
            if not candidate.is_absolute():
                candidate = self.execution_root / candidate
            return load_workflow(candidate)
        if request.task_text:
            title = request.title or "OpenTask run"
            return build_starter_workflow(title, request.task_text)
        raise ValueError("one of workflowPath, workflowMarkdown, or taskText is required")

    async def _bootstrap_openclaw(
        self,
        state: RunState,
        refs: RunRefs,
        parsed,
        planner_prompt: str,
        driver_prompt: str,
    ) -> RunState:
        state, refs = self._normalize_session_keys(state, refs, parsed.definition)
        planner_run = await self.gateway.send_chat(
            session_key=state.planner_session_key,
            message=planner_prompt,
            idempotency_key=f"{state.run_id}-planner",
            timeout_ms=self.settings.default_tick_timeout_ms,
        )
        refs.node_run_ids["planner"] = str(planner_run.get("runId") or planner_run.get("id") or "")
        self.store.append_event(
            state.run_id,
            RunEvent(
                event="plan.generated",
                runId=state.run_id,
                message="Planner session bootstrapped.",
                payload={"plannerSessionKey": state.planner_session_key},
            ),
        )

        cron_response = await self.gateway.cron_add(
            {
                "name": f"OpenTask driver {state.run_id}",
                "schedule": {"kind": "cron", "expr": parsed.definition.driver.cron},
                "sessionTarget": state.driver_session_key,
                "wakeMode": parsed.definition.driver.wake_mode,
                "payload": {
                    "kind": "agentTurn",
                    "message": driver_prompt,
                    "lightContext": False,
                },
                "delivery": {"mode": "none"},
            }
        )
        cron_job_id = str(
            cron_response.get("jobId")
            or cron_response.get("id")
            or cron_response.get("job", {}).get("id")
            or ""
        )
        refs = refs.model_copy(update={"cron_job_id": cron_job_id})
        state = state.model_copy(update={"cron_job_id": cron_job_id})
        self.store.write_run_refs(state.run_id, refs)
        self.store.write_state(self.store.update_state_timestamp(state, last_event="plan.generated"))
        return self.store.load_state(state.run_id)

    async def _sync_running_nodes(self, state: RunState) -> RunState:
        updated_nodes: list[NodeState] = []
        changed = False
        for node in state.nodes:
            if node.status != "running" or not node.run_id:
                updated_nodes.append(node)
                continue
            result = await self.gateway.wait_run(node.run_id, timeout_ms=0)
            status = result.get("status")
            if status in {None, "accepted", "started", "timeout"}:
                updated_nodes.append(node)
                continue
            changed = True
            if status == "ok":
                artifact_paths = await self._artifact_paths_after_completion(state.run_id, node, result)
                completed_node = node.model_copy(
                    update={
                        "status": "completed",
                        "completed_at": utc_now(),
                        "notes": [*node.notes, "Completed by OpenClaw run."],
                        "artifact_paths": artifact_paths,
                    }
                )
                updated_nodes.append(completed_node)
                self._write_node_result(
                    state.run_id,
                    completed_node,
                    summary="Node completed.",
                    payload=result,
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.completed",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Node completed.",
                        payload=result,
                    ),
                )
            else:
                failed_node = node.model_copy(
                    update={
                        "status": "failed",
                        "completed_at": utc_now(),
                        "notes": [*node.notes, json.dumps(result, ensure_ascii=True)],
                    }
                )
                updated_nodes.append(failed_node)
                self._write_node_result(
                    state.run_id,
                    failed_node,
                    summary="Node failed.",
                    payload=result,
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.failed",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Node failed.",
                        payload=result,
                    ),
                )

        if not changed:
            return state
        return self.store.update_state_timestamp(
            state.model_copy(update={"nodes": updated_nodes}),
            last_event="node.completed",
        )

    async def _sync_driver_run(self, run_id: str, refs: RunRefs) -> RunRefs:
        if not refs.driver_run_id:
            return refs

        try:
            result = await self.gateway.wait_run(refs.driver_run_id, timeout_ms=0)
        except OpenClawGatewayError as exc:
            self.store.append_event(
                run_id,
                RunEvent(
                    event="driver.status.unavailable",
                    runId=run_id,
                    message=f"Driver status check failed: {exc}",
                    payload={"runId": refs.driver_run_id},
                ),
            )
            return refs
        status = result.get("status")
        if status in {None, "accepted", "started", "timeout"}:
            return refs

        event_name = "driver.completed" if status == "ok" else "driver.failed"
        self.store.append_event(
            run_id,
            RunEvent(
                event=event_name,
                runId=run_id,
                message=f"Driver run {refs.driver_run_id} finished with status={status}.",
                payload={"runId": refs.driver_run_id, "result": result},
            ),
        )
        next_refs = refs.model_copy(update={"driver_run_id": None})
        self.store.write_run_refs(run_id, next_refs)
        return next_refs

    async def _apply_control_actions(self, state: RunState, refs: RunRefs) -> tuple[RunState, RunRefs]:
        actions = self.store.load_control_actions(state.run_id)
        pending_actions = [action for action in actions if action.id not in refs.applied_control_ids]
        if not pending_actions:
            return state, refs

        next_state = state
        next_refs = refs
        for action in pending_actions:
            if action.action == "pause":
                if next_refs.cron_job_id:
                    await self.gateway.cron_update(next_refs.cron_job_id, {"enabled": False})
                next_state = self.store.update_state_timestamp(
                    next_state.model_copy(update={"status": "paused"}),
                    last_event="run.paused",
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(event="run.paused", runId=state.run_id, message="Paused from control queue."),
                )
            elif action.action == "resume":
                if next_refs.cron_job_id:
                    await self.gateway.cron_update(next_refs.cron_job_id, {"enabled": True})
                next_state = self.store.update_state_timestamp(
                    next_state.model_copy(update={"status": "running"}),
                    last_event="run.resumed",
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(event="run.resumed", runId=state.run_id, message="Resumed from control queue."),
                )
            elif action.action == "retry":
                if not action.node_id:
                    raise ValueError("retry control action requires nodeId")
                next_state = self._apply_retry(next_state, action.node_id)
            elif action.action == "skip":
                if not action.node_id:
                    raise ValueError("skip control action requires nodeId")
                next_state = self._apply_skip(next_state, action.node_id)
            elif action.action == "approve":
                if not action.node_id:
                    raise ValueError("approve control action requires nodeId")
                next_state = self._apply_approve(next_state, action.node_id)
            elif action.action == "send_message":
                next_state = await self._apply_send_message(next_state, next_refs, action.message or "")
            elif action.action == "patch_cron":
                if next_refs.cron_job_id:
                    await self.gateway.cron_update(next_refs.cron_job_id, action.patch)
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="cron.patched",
                        runId=state.run_id,
                        message="Patched cron job from control queue.",
                        payload=action.patch,
                    ),
                )
            next_refs = next_refs.model_copy(
                update={"applied_control_ids": [*next_refs.applied_control_ids, action.id]}
            )

        return next_state, next_refs

    def _apply_retry(self, state: RunState, node_id: str) -> RunState:
        nodes = []
        for node in state.nodes:
            if node.id == node_id:
                nodes.append(
                    node.model_copy(
                        update={
                            "status": "pending",
                            "run_id": None,
                            "session_key": None,
                            "child_session_key": None,
                            "started_at": None,
                            "completed_at": None,
                            "notes": [*node.notes, "Retried from control queue."],
                        }
                    )
                )
            else:
                nodes.append(node)
        next_state = self.store.update_state_timestamp(
            state.model_copy(update={"status": "running", "nodes": nodes}),
            last_event="node.retry",
        )
        self.store.append_event(
            state.run_id,
            RunEvent(event="node.ready", runId=state.run_id, nodeId=node_id, message="Node retried."),
        )
        return next_state

    def _apply_skip(self, state: RunState, node_id: str) -> RunState:
        nodes = []
        for node in state.nodes:
            if node.id == node_id:
                nodes.append(
                    node.model_copy(
                        update={
                            "status": "skipped",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, "Skipped from control queue."],
                        }
                    )
                )
            else:
                nodes.append(node)
        next_state = self.store.update_state_timestamp(
            state.model_copy(update={"nodes": nodes}),
            last_event="node.skipped",
        )
        skipped_node = next(node for node in next_state.nodes if node.id == node_id)
        self._write_node_result(
            state.run_id,
            skipped_node,
            summary="Node skipped.",
            payload={"action": "skip"},
        )
        self.store.append_event(
            state.run_id,
            RunEvent(event="node.skipped", runId=state.run_id, nodeId=node_id, message="Node skipped."),
        )
        return next_state

    def _apply_approve(self, state: RunState, node_id: str) -> RunState:
        nodes = []
        for node in state.nodes:
            if node.id == node_id:
                nodes.append(
                    node.model_copy(
                        update={
                            "status": "completed",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, "Approved from control queue."],
                        }
                    )
                )
            else:
                nodes.append(node)
        next_state = self.store.update_state_timestamp(
            state.model_copy(update={"nodes": nodes}),
            last_event="node.approved",
        )
        approved_node = next(node for node in next_state.nodes if node.id == node_id)
        self._write_node_result(
            state.run_id,
            approved_node,
            summary="Approval gate completed by operator.",
            payload={"action": "approve"},
        )
        self.store.append_event(
            state.run_id,
            RunEvent(
                event="node.completed",
                runId=state.run_id,
                nodeId=node_id,
                message="Approval gate completed by operator.",
            ),
        )
        return next_state

    async def _apply_send_message(self, state: RunState, refs: RunRefs, message: str) -> RunState:
        if not refs.delivery_context or not refs.delivery_context.channel or not refs.delivery_context.to:
            raise ValueError("send_message control action requires deliveryContext.channel and deliveryContext.to")
        await self.gateway.send_outbound_message(
            session_key=refs.root_session_key or state.root_session_key or state.driver_session_key or "",
            channel=refs.delivery_context.channel,
            to=refs.delivery_context.to,
            message=message,
            account_id=refs.delivery_context.account_id,
            thread_id=refs.delivery_context.thread_id,
        )
        next_state = self.store.update_state_timestamp(
            state.model_copy(
                update={
                    "last_progress_message": message,
                    "last_progress_message_at": utc_now(),
                }
            ),
            last_event="run.message.sent",
        )
        self.store.append_event(
            state.run_id,
            RunEvent(
                event="run.message.sent",
                runId=state.run_id,
                message="Sent an explicit update to the source delivery context.",
                payload={"message": message},
            ),
        )
        return next_state

    async def _maybe_emit_progress_update(self, state: RunState, refs: RunRefs) -> tuple[RunState, RunRefs]:
        if not refs.delivery_context or not refs.delivery_context.channel or not refs.delivery_context.to:
            return state, refs

        events = self.store.load_events(state.run_id)
        recent_events = events[refs.last_progress_event_count :]
        if any(event.event == "run.message.sent" for event in recent_events):
            return state, refs.model_copy(update={"last_progress_event_count": len(events)})
        sendable_events = [event for event in recent_events if event.event in PROGRESS_EVENTS]
        if not sendable_events:
            return state, refs.model_copy(update={"last_progress_event_count": len(events)})

        message = self._build_progress_message(state, sendable_events)
        try:
            await self.gateway.send_outbound_message(
                session_key=refs.root_session_key or state.root_session_key or state.driver_session_key or "",
                channel=refs.delivery_context.channel,
                to=refs.delivery_context.to,
                message=message,
                account_id=refs.delivery_context.account_id,
                thread_id=refs.delivery_context.thread_id,
            )
        except OpenClawGatewayError as exc:
            self.store.append_event(
                state.run_id,
                RunEvent(
                    event="run.progress.failed",
                    runId=state.run_id,
                    message=f"Failed to emit progress update: {exc}",
                ),
            )
            return state, refs.model_copy(update={"last_progress_event_count": len(events)})

        progress_event = RunEvent(
            event="run.progress.sent",
            runId=state.run_id,
            message="Sent an automatic progress update to the source delivery context.",
            payload={"message": message},
        )
        self.store.append_event(state.run_id, progress_event)
        next_state = self.store.update_state_timestamp(
            state.model_copy(
                update={
                    "last_progress_message": message,
                    "last_progress_message_at": progress_event.timestamp,
                }
            ),
            last_event="run.progress.sent",
        )
        next_refs = refs.model_copy(update={"last_progress_event_count": len(events) + 1})
        return next_state, next_refs

    def _build_progress_message(self, state: RunState, events: list[RunEvent]) -> str:
        lines = [f"[OpenTask] {state.title} ({state.run_id})", f"Status: {state.status}", ""]
        for event in events[-4:]:
            node_part = f" [{event.node_id}]" if event.node_id else ""
            message = event.message or event.event
            lines.append(f"- {event.event}{node_part}: {message}")
        return "\n".join(lines)

    async def _apply_driver_directives(
        self,
        state: RunState,
        workflow,
    ) -> tuple[RunState, object]:
        handled_ids = self._handled_driver_directive_ids(state.run_id)
        try:
            history = await self.gateway.chat_history(state.driver_session_key, limit=20)
        except OpenClawGatewayError as exc:
            self.store.append_event(
                state.run_id,
                RunEvent(
                    event="driver.history.unavailable",
                    runId=state.run_id,
                    message=f"Driver history unavailable: {exc}",
                ),
            )
            return state, workflow
        directives = [directive for directive in extract_driver_directives(history) if directive.id not in handled_ids]
        if not directives:
            return state, workflow

        next_state = state
        next_workflow = workflow
        changed = False

        for directive in directives:
            try:
                next_state, next_workflow = self._apply_driver_directive(next_state, next_workflow, directive)
            except Exception as exc:
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="driver.directive.rejected",
                        runId=state.run_id,
                        message=f"Rejected driver directive {directive.id}: {exc}",
                        payload={"directiveId": directive.id, "summary": directive.summary or ""},
                    ),
                )
                continue

            changed = True
            self.store.append_event(
                state.run_id,
                RunEvent(
                    event="driver.directive.applied",
                    runId=state.run_id,
                    message=f"Applied driver directive {directive.id}.",
                    payload={
                        "directiveId": directive.id,
                        "summary": directive.summary or "",
                        "mutations": [
                            mutation.model_dump(by_alias=True, exclude_none=True)
                            for mutation in directive.mutations
                        ],
                    },
                ),
            )

        if not changed:
            return state, workflow

        self.store.write_workflow_lock(state.run_id, next_workflow)
        next_state = self.store.update_state_timestamp(next_state, last_event="driver.directive.applied")
        return next_state, next_workflow

    async def _maybe_request_driver_turn(
        self,
        state: RunState,
        workflow,
        refs: RunRefs,
    ) -> RunRefs:
        if state.status != "running" or refs.driver_run_id:
            return refs

        nonterminal_nodes = [node for node in state.nodes if node.status not in TERMINAL_STATUSES]
        if not nonterminal_nodes:
            return refs

        event_count = len(self.store.load_events(state.run_id))
        activity_count = self._driver_activity_count(state.run_id)
        if activity_count <= refs.driver_requested_activity_count:
            return refs

        prompt = self._build_driver_turn_prompt(state, workflow)
        self.store.write_support_file(state.run_id, "driver.context.md", prompt)
        run_id = f"{state.run_id}-driver-{uuid4().hex[:8]}"
        try:
            response = await self.gateway.send_chat(
                session_key=state.driver_session_key,
                message=prompt,
                idempotency_key=run_id,
                timeout_ms=workflow.definition.driver.timeout_ms,
                thinking="low",
            )
        except OpenClawGatewayError as exc:
            self.store.append_event(
                state.run_id,
                RunEvent(
                    event="driver.request.failed",
                    runId=state.run_id,
                    message=f"Driver request failed: {exc}",
                ),
            )
            return refs
        resolved_run_id = str(response.get("runId") or response.get("id") or run_id)
        next_refs = refs.model_copy(
            update={
                "driver_run_id": resolved_run_id,
                "driver_requested_event_count": event_count,
                "driver_requested_activity_count": activity_count,
            }
        )
        self.store.append_event(
            state.run_id,
            RunEvent(
                event="driver.requested",
                runId=state.run_id,
                message="Requested autonomous driver review.",
                payload={"runId": resolved_run_id, "response": response},
            ),
        )
        self.store.write_run_refs(state.run_id, next_refs)
        return next_refs

    def _driver_activity_count(self, run_id: str) -> int:
        events = self.store.load_events(run_id)
        return sum(1 for event in events if event.event not in DRIVER_BOOKKEEPING_EVENTS)

    def _advance_waiting_nodes(self, state: RunState) -> RunState:
        changed = False
        updated_nodes: list[NodeState] = []
        run_dir = self.store.runs_root / state.run_id

        for node in state.nodes:
            if node.status != "waiting":
                updated_nodes.append(node)
                continue

            if node.kind == "approval":
                updated_nodes.append(node)
                continue

            wait_for = node.wait_for
            if wait_for is None:
                updated_nodes.append(node)
                continue

            if wait_for.type == "next_tick" and node.started_at:
                changed = True
                completed_node = node.model_copy(
                    update={
                        "status": "completed",
                        "completed_at": utc_now(),
                        "notes": [*node.notes, "next_tick condition satisfied."],
                    }
                )
                updated_nodes.append(completed_node)
                self._write_node_result(
                    state.run_id,
                    completed_node,
                    summary="Wait node completed on next tick.",
                    payload={"waitType": "next_tick"},
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.completed",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Wait node completed on next tick.",
                    ),
                )
                continue

            if wait_for.type == "file_exists" and wait_for.path and (run_dir / wait_for.path).exists():
                changed = True
                completed_node = node.model_copy(
                    update={
                        "status": "completed",
                        "completed_at": utc_now(),
                        "notes": [*node.notes, f"Detected file {wait_for.path}."],
                    }
                )
                updated_nodes.append(completed_node)
                self._write_node_result(
                    state.run_id,
                    completed_node,
                    summary=f"Wait node detected file {wait_for.path}.",
                    payload={"waitType": "file_exists", "path": wait_for.path},
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.completed",
                        runId=state.run_id,
                        nodeId=node.id,
                        message=f"Wait node detected file {wait_for.path}.",
                    ),
                )
                continue

            updated_nodes.append(node)

        if not changed:
            return state
        return self.store.update_state_timestamp(
            state.model_copy(update={"nodes": updated_nodes}),
            last_event="node.completed",
        )

    def _apply_driver_directive(self, state: RunState, workflow, directive) -> tuple[RunState, object]:
        definition = workflow.definition
        workflow_nodes = list(definition.nodes)
        state_nodes = list(state.nodes)
        state_by_id = {node.id: node for node in state_nodes}

        for mutation in directive.mutations:
            if mutation.kind == "add_node":
                if any(node.id == mutation.node.id for node in workflow_nodes):
                    raise ValueError(f"node already exists: {mutation.node.id}")
                insert_at = next(
                    (index for index, workflow_node in enumerate(workflow_nodes) if workflow_node.kind == "summary"),
                    len(workflow_nodes),
                )
                next_workflow_nodes = [
                    *workflow_nodes[:insert_at],
                    mutation.node,
                    *workflow_nodes[insert_at:],
                ]
                validate_workflow_definition(definition.model_copy(update={"nodes": next_workflow_nodes}))
                workflow_nodes = next_workflow_nodes
                state_nodes = [
                    *state_nodes[:insert_at],
                    self._node_state_from_definition(mutation.node),
                    *state_nodes[insert_at:],
                ]
                self._ensure_node_runtime_dir(state.run_id, state_nodes[insert_at])
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.added",
                        runId=state.run_id,
                        nodeId=mutation.node.id,
                        message=f"Driver added node {mutation.node.id}.",
                        payload=mutation.node.model_dump(by_alias=True, exclude_none=True),
                    ),
                )
                state_by_id[mutation.node.id] = state_nodes[-1]
                continue

            target = state_by_id.get(mutation.node_id)
            if target is None:
                raise ValueError(f"unknown node for rewire: {mutation.node_id}")
            if target.status not in {"pending", "ready"}:
                raise ValueError(
                    f"cannot rewire node {mutation.node_id} while status={target.status}"
                )

            updated_workflow_nodes: list[WorkflowDefinition | object] = []
            updated_state_nodes: list[NodeState] = []
            for workflow_node in workflow_nodes:
                if workflow_node.id == mutation.node_id:
                    updated_workflow_nodes.append(workflow_node.model_copy(update={"needs": mutation.needs}))
                else:
                    updated_workflow_nodes.append(workflow_node)
            validate_workflow_definition(definition.model_copy(update={"nodes": updated_workflow_nodes}))

            for state_node in state_nodes:
                if state_node.id == mutation.node_id:
                    updated_state = state_node.model_copy(
                        update={
                            "needs": mutation.needs,
                            "status": "pending",
                            "notes": [*state_node.notes, "Rewired by driver directive."],
                        }
                    )
                    updated_state_nodes.append(updated_state)
                    state_by_id[mutation.node_id] = updated_state
                else:
                    updated_state_nodes.append(state_node)
            workflow_nodes = list(updated_workflow_nodes)
            state_nodes = updated_state_nodes
            self.store.append_event(
                state.run_id,
                RunEvent(
                    event="node.rewired",
                    runId=state.run_id,
                    nodeId=mutation.node_id,
                    message=f"Driver rewired node {mutation.node_id}.",
                    payload={"needs": mutation.needs},
                ),
            )

        updated_definition = definition.model_copy(update={"nodes": workflow_nodes})
        validate_workflow_definition(updated_definition)
        updated_workflow = workflow.model_copy(update={"definition": updated_definition})
        updated_state = state.model_copy(update={"nodes": state_nodes})
        return updated_state, updated_workflow

    def _promote_ready_nodes(self, state: RunState) -> RunState:
        status_by_id = {node.id: node.status for node in state.nodes}
        changed = False
        updated_nodes: list[NodeState] = []
        for node in state.nodes:
            if node.status != "pending":
                updated_nodes.append(node)
                continue
            if all(status_by_id.get(dep) in TERMINAL_STATUSES for dep in node.needs):
                changed = True
                updated_nodes.append(node.model_copy(update={"status": "ready"}))
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.ready",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Dependencies satisfied; node is ready.",
                    ),
                )
            else:
                updated_nodes.append(node)
        if not changed:
            return state
        return self.store.update_state_timestamp(
            state.model_copy(update={"nodes": updated_nodes}),
            last_event="node.ready",
        )

    async def _dispatch_ready_nodes(
        self,
        state: RunState,
        workflow_definition: WorkflowDefinition,
        refs: RunRefs,
    ) -> RunState:
        definitions = {node.id: node for node in workflow_definition.nodes}
        workflow_defaults = workflow_definition.defaults
        changed = False
        updated_nodes: list[NodeState] = []

        for node in state.nodes:
            if node.status != "ready":
                updated_nodes.append(node)
                continue
            if refs.driver_run_id:
                updated_nodes.append(node)
                continue
            definition = definitions[node.id]
            if node.kind == "approval":
                changed = True
                updated_nodes.append(
                    node.model_copy(
                        update={
                            "status": "waiting",
                            "started_at": utc_now(),
                            "notes": [*node.notes, "Waiting for operator approval."],
                        }
                    )
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.waiting",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Approval gate opened.",
                    ),
                )
                continue

            if node.kind == "wait":
                changed = True
                updated_nodes.append(
                    node.model_copy(
                        update={
                            "status": "waiting",
                            "started_at": utc_now(),
                            "notes": [*node.notes, "Entering wait state."],
                        }
                    )
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.waiting",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Wait node entered waiting state.",
                    ),
                )
                continue

            if node.kind == "summary":
                changed = True
                report_path = self._write_summary_report(state.run_id, state)
                artifact_paths = node.artifact_paths if report_path in node.artifact_paths else [*node.artifact_paths, report_path]
                completed_node = node.model_copy(
                    update={
                        "status": "completed",
                        "completed_at": utc_now(),
                        "artifact_paths": artifact_paths,
                    }
                )
                updated_nodes.append(completed_node)
                self._write_node_result(
                    state.run_id,
                    completed_node,
                    summary="Summary node completed.",
                    payload={"artifacts": artifact_paths},
                )
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.completed",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Summary node completed.",
                    ),
                )
                continue

            timeout_ms = (
                definition.timeout_ms
                or workflow_defaults.timeout_ms
                or self.settings.default_tick_timeout_ms
            )
            execution_prompt = self._build_node_execution_prompt(state, node, definition)
            if node.kind == "subagent":
                parent_session_key = self._effective_session_key(
                    definition.session_key or state.driver_session_key,
                    workflow_defaults.agent_id,
                )
                if node.working_memory and node.working_memory.handoff:
                    self.store.write_support_file(state.run_id, node.working_memory.handoff, execution_prompt)
                response = await self.gateway.spawn_session(
                    parent_session_key=parent_session_key,
                    task=execution_prompt,
                    label=node.title,
                    agent_id=workflow_defaults.agent_id,
                    model=workflow_defaults.model,
                    thinking=workflow_defaults.thinking,
                    cwd=str(self.execution_root),
                    timeout_seconds=max(1, (timeout_ms + 999) // 1000),
                )
                child_session_key = str(response.get("childSessionKey") or "")
                payload_update = {
                    "status": "running",
                    "started_at": utc_now(),
                    "run_id": str(response.get("runId") or ""),
                    "session_key": parent_session_key,
                    "child_session_key": child_session_key or None,
                }
                updated = node.model_copy(update=payload_update)
                refs.node_run_ids[node.id] = updated.run_id or ""
                refs.node_sessions[node.id] = parent_session_key
                if child_session_key:
                    refs.child_sessions[node.id] = child_session_key
                changed = True
                updated_nodes.append(updated)
                self.store.append_event(
                    state.run_id,
                    RunEvent(
                        event="node.started",
                        runId=state.run_id,
                        nodeId=node.id,
                        message="Subagent node spawned via sessions_spawn.",
                        payload={
                            "parentSessionKey": parent_session_key,
                            "response": response,
                        },
                    ),
                )
                continue

            session_key = self._effective_session_key(
                definition.session_key
                or self._session_key_for_node(
                    state.run_id,
                    node.id,
                    node.kind,
                    workflow_defaults.agent_id,
                ),
                workflow_defaults.agent_id,
            )
            run_id = f"{state.run_id}-{node.id}-{uuid4().hex[:8]}"
            response = await self.gateway.send_chat(
                session_key=session_key,
                message=execution_prompt,
                idempotency_key=run_id,
                timeout_ms=timeout_ms,
                thinking=workflow_defaults.thinking,
            )
            gateway_status = response.get("status")
            payload_update = {
                "status": "running" if gateway_status in {None, "accepted", "started", "timeout"} else "completed",
                "started_at": utc_now(),
                "run_id": str(response.get("runId") or response.get("id") or run_id),
                "session_key": session_key,
            }
            updated = node.model_copy(update=payload_update)
            refs.node_run_ids[node.id] = updated.run_id or run_id
            refs.node_sessions[node.id] = session_key
            changed = True
            updated_nodes.append(updated)
            self.store.append_event(
                state.run_id,
                RunEvent(
                    event="node.started",
                    runId=state.run_id,
                    nodeId=node.id,
                    message="Node dispatched to OpenClaw.",
                    payload={"sessionKey": session_key, "response": response},
                ),
            )
            if gateway_status == "ok":
                artifact_paths = await self._artifact_paths_after_completion(state.run_id, updated, response)
                updated_nodes[-1] = updated.model_copy(
                    update={
                        "status": "completed",
                        "completed_at": utc_now(),
                        "artifact_paths": artifact_paths,
                    }
                )

        if not changed:
            return state
        self.store.write_run_refs(state.run_id, refs)
        return self.store.update_state_timestamp(
            state.model_copy(update={"nodes": updated_nodes}),
            last_event="node.started",
        )

    async def _finalize_if_terminal(self, state: RunState) -> RunState:
        statuses = {node.status for node in state.nodes}
        if not statuses.issubset(TERMINAL_STATUSES):
            return state

        refs = self.store.load_run_refs(state.run_id)
        if refs.cron_job_id:
            await self.gateway.cron_update(refs.cron_job_id, {"enabled": False})

        run_status = "failed" if "failed" in statuses else "completed"
        final_state = self.store.update_state_timestamp(
            state.model_copy(update={"status": run_status}),
            last_event="run.completed",
        )
        self.store.append_event(
            state.run_id,
            RunEvent(
                event="run.completed",
                runId=state.run_id,
                message=f"Run entered terminal state: {run_status}.",
            ),
        )
        return final_state

    async def _artifact_paths_after_completion(self, run_id: str, node: NodeState, payload: dict) -> list[str]:
        if node.outputs_mode != "report":
            return node.artifact_paths
        run_dir = self.store.runs_root / run_id
        report_artifact = next(
            (
                artifact
                for artifact in node.artifact_paths
                if Path(artifact).name == "report.md"
            ),
            None,
        )
        if report_artifact and (run_dir / report_artifact).exists():
            return node.artifact_paths
        session_key = node.child_session_key or node.session_key
        if session_key:
            try:
                history = await self.gateway.chat_history(session_key, limit=100)
            except OpenClawGatewayError as exc:
                self.store.append_event(
                    run_id,
                    RunEvent(
                        event="node.history.unavailable",
                        runId=run_id,
                        nodeId=node.id,
                        message=f"Node history unavailable: {exc}",
                    ),
                )
            else:
                report = extract_last_assistant_final_text(history)
                if report:
                    artifact = self.store.write_node_report(run_id, node.id, "report.md", report)
                    if artifact in node.artifact_paths:
                        return node.artifact_paths
                    return [*node.artifact_paths, artifact]
        return self._artifact_paths_after_payload_summary(run_id, node, payload)

    def _artifact_paths_after_payload_summary(self, run_id: str, node: NodeState, payload: dict) -> list[str]:
        if node.outputs_mode != "report":
            return node.artifact_paths
        report = "\n".join(
            [
                f"# {node.title}",
                "",
                f"- Status: {payload.get('status', 'ok')}",
                f"- Session: {node.child_session_key or node.session_key or 'n/a'}",
                f"- Run ID: {node.run_id or 'n/a'}",
                "",
                "```json",
                json.dumps(payload, indent=2, ensure_ascii=True),
                "```",
            ]
        )
        artifact = self.store.write_node_report(run_id, node.id, "report.md", report)
        if artifact in node.artifact_paths:
            return node.artifact_paths
        return [*node.artifact_paths, artifact]

    def _write_summary_report(self, run_id: str, state: RunState) -> str:
        lines = [f"# Run {run_id}", "", f"- Workflow: {state.workflow_id}", f"- Status: {state.status}", ""]
        for node in state.nodes:
            lines.extend(
                [
                    f"## {node.title}",
                    f"- Kind: {node.kind}",
                    f"- Status: {node.status}",
                    f"- Artifacts: {', '.join(node.artifact_paths) if node.artifact_paths else 'none'}",
                    "",
                ]
            )
        return self.store.write_node_report(run_id, "summary", "report.md", "\n".join(lines))

    def _write_node_result(self, run_id: str, node: NodeState, *, summary: str, payload: dict) -> None:
        self.store.write_node_result(
            run_id,
            node.id,
            NodeResult(
                runId=run_id,
                nodeId=node.id,
                status=node.status,
                summary=summary,
                artifacts=node.artifact_paths,
                sessionKey=node.session_key,
                childSessionKey=node.child_session_key,
                workingMemory=node.working_memory,
                payload=payload,
            ),
        )

    def _build_planner_prompt(self, run_id: str, body: str) -> str:
        run_dir = self._run_dir_rel(run_id)
        return (
            f"You are the root orchestrator session for OpenTask run {run_id}.\n"
            f"Workspace root: {self.execution_root}\n"
            f"Run directory: {run_dir}\n"
            f"Review the frozen workflow at {run_dir}/workflow.lock.md, refs at {run_dir}/refs.json, and pending controls at {run_dir}/control.jsonl.\n"
            "Do not overwrite workflow.lock.md directly; use it as the frozen execution plan and let OpenTask apply explicit mutations.\n\n"
            f"{body}".strip()
        )

    def _build_driver_prompt(self, run_id: str) -> str:
        run_dir = self._run_dir_rel(run_id)
        return (
            f"You are the idempotent root orchestrator for OpenTask run {run_id}.\n"
            f"Workspace root: {self.execution_root}\n"
            f"Run directory: {run_dir}\n"
            f"On each tick, read {run_dir}/workflow.lock.md, {run_dir}/state.json, {run_dir}/refs.json, {run_dir}/control.jsonl, and {run_dir}/nodes/* artifacts.\n"
            f"Never repeat completed nodes. Advance only ready nodes, inspect running nodes, and express graph changes through mutation directives that OpenTask records in {run_dir}/events.jsonl.\n"
            f"{driver_mutation_instructions()}"
        )

    def _build_driver_turn_prompt(self, state: RunState, workflow) -> str:
        run_dir = self._run_dir_rel(state.run_id)
        node_lines = []
        for node in state.nodes:
            needs = ", ".join(node.needs) if node.needs else "none"
            artifacts = ", ".join(node.artifact_paths) if node.artifact_paths else "none"
            node_lines.append(
                f"- {node.id} | kind={node.kind} | status={node.status} | needs={needs} | artifacts={artifacts}"
            )

        recent_events = self.store.load_events(state.run_id, limit=8)
        event_lines = [
            f"- {event.event}"
            + (f" node={event.node_id}" if event.node_id else "")
            + (f" msg={event.message}" if event.message else "")
            for event in recent_events
        ]

        artifact_sections = []
        for node in state.nodes:
            if node.outputs_mode != "report" or node.status not in TERMINAL_STATUSES:
                continue
            for artifact in node.artifact_paths:
                if not artifact.endswith(".md"):
                    continue
                artifact_path = self.store.runs_root / state.run_id / artifact
                if not artifact_path.exists():
                    continue
                preview = artifact_path.read_text(encoding="utf-8")[:1200].strip()
                if not preview:
                    continue
                artifact_sections.append(f"## {artifact}\n\n{preview}")

        body = workflow.body.strip() or "(none)"
        sections = [
            f"You are the autonomous workflow driver for OpenTask run {state.run_id}.",
            "Review the current workflow snapshot and decide whether the graph should change.",
            "If you want no graph changes, reply exactly NO_CHANGE.",
            driver_mutation_instructions(),
            "",
            f"Workflow ID: {state.workflow_id}",
            f"Title: {state.title}",
            f"Run directory: {run_dir}",
            "",
            "Workflow body:",
            body,
            "",
            "Current nodes:",
            "\n".join(node_lines) if node_lines else "- none",
            "",
            "Recent events:",
            "\n".join(event_lines) if event_lines else "- none",
        ]
        if artifact_sections:
            sections.extend(["", "Artifact previews:", "\n\n".join(artifact_sections)])
        return "\n".join(sections).strip() + "\n"

    def _build_node_execution_prompt(self, state: RunState, node: NodeState, definition) -> str:
        run_dir = self._run_dir_rel(state.run_id)
        sections = [
            f"You are executing OpenTask node {node.id} for run {state.run_id}.",
            f"Workspace root: {self.execution_root}",
            f"Run directory: {run_dir}",
            f"Workflow snapshot: {run_dir}/workflow.lock.md",
            f"Run state projection: {run_dir}/state.json",
            f"Run refs: {run_dir}/refs.json",
            "Do not modify workflow.lock.md, state.json, refs.json, or events.jsonl directly.",
        ]

        dependency_artifacts: list[str] = []
        state_by_id = {item.id: item for item in state.nodes}
        for dependency in node.needs:
            dependency_node = state_by_id.get(dependency)
            if dependency_node is None:
                continue
            dependency_artifacts.extend(
                f"{run_dir}/{artifact}" for artifact in dependency_node.artifact_paths
            )

        if dependency_artifacts:
            sections.extend(
                [
                    "",
                    "Review these dependency artifacts before replying:",
                    "\n".join(f"- {artifact}" for artifact in dependency_artifacts),
                ]
            )

        if node.outputs_mode == "report":
            sections.extend(
                [
                    "",
                    "Produce a report for this node.",
                    "Preferred artifact paths:",
                    "\n".join(f"- {run_dir}/{artifact}" for artifact in node.artifact_paths)
                    if node.artifact_paths
                    else "- none",
                    "If you cannot write files directly, include the full report in your final assistant message.",
                ]
            )
        else:
            sections.extend(
                [
                    "",
                    "Reply with a concise completion update for this node.",
                ]
            )

        if node.working_memory is not None:
            memory_lines = [
                f"- plan: {run_dir}/{node.working_memory.plan}",
                f"- findings: {run_dir}/{node.working_memory.findings}",
                f"- progress: {run_dir}/{node.working_memory.progress}",
            ]
            if node.working_memory.handoff:
                memory_lines.append(f"- handoff: {run_dir}/{node.working_memory.handoff}")
            sections.extend(
                [
                    "",
                    "Node-local working memory files:",
                    "\n".join(memory_lines),
                    "If this node expands into multiple concrete steps, keep these files updated instead of creating ad-hoc planning files elsewhere.",
                ]
            )

        sections.extend(["", "Task:", definition.prompt.strip() or "(no task prompt)"])
        return "\n".join(sections).strip() + "\n"

    def _handled_driver_directive_ids(self, run_id: str) -> set[str]:
        handled: set[str] = set()
        for event in self.store.load_events(run_id):
            if event.event not in {"driver.directive.applied", "driver.directive.rejected"}:
                continue
            directive_id = event.payload.get("directiveId")
            if isinstance(directive_id, str) and directive_id:
                handled.add(directive_id)
        return handled

    def _ensure_node_runtime_dir(self, run_id: str, node: NodeState) -> None:
        self.store.ensure_node_runtime_files(run_id, node)

    def _node_state_from_definition(self, node) -> NodeState:
        artifact_paths = ensure_relative_paths(normalize_artifact_paths(node))
        return NodeState(
            id=node.id,
            title=node.title,
            kind=node.kind,
            status="pending",
            needs=node.needs,
            outputsMode=node.outputs.mode,
            artifactPaths=artifact_paths,
            workingMemory=self.store.node_working_memory_paths(node.id, node.kind),
            waitFor=node.wait_for,
        )

    def _lock_for_run(self, run_id: str) -> asyncio.Lock:
        lock = self._run_locks.get(run_id)
        if lock is None:
            lock = asyncio.Lock()
            self._run_locks[run_id] = lock
        return lock

    @asynccontextmanager
    async def _run_scope(self, run_id: str):
        async with self._lock_for_run(run_id):
            async with self.run_file_lock.hold(run_id):
                yield

    def _session_key_for_node(self, run_id: str, node_id: str, kind: str, agent_id: str) -> str:
        suffix = "subagent" if kind == "subagent" else "node"
        return qualify_agent_session_key(
            f"session:workflow:{run_id}:{suffix}:{node_id}",
            agent_id,
        )

    def _normalize_session_keys(
        self,
        state: RunState,
        refs: RunRefs,
        workflow_definition: WorkflowDefinition,
    ) -> tuple[RunState, RunRefs]:
        agent_id = workflow_definition.defaults.agent_id
        normalized_nodes: list[NodeState] = []
        nodes_changed = False
        for node in state.nodes:
            if not node.session_key:
                normalized_nodes.append(node)
                continue
            normalized_session_key = self._effective_session_key(node.session_key, agent_id)
            if normalized_session_key == node.session_key:
                normalized_nodes.append(node)
                continue
            nodes_changed = True
            normalized_nodes.append(node.model_copy(update={"session_key": normalized_session_key}))

        normalized_state = state.model_copy(
            update={
                "source_session_key": self._normalize_optional_session_key(state.source_session_key, agent_id),
                "root_session_key": self._normalize_optional_session_key(state.root_session_key, agent_id),
                "planner_session_key": self._normalize_optional_session_key(state.planner_session_key, agent_id),
                "driver_session_key": self._normalize_optional_session_key(state.driver_session_key, agent_id),
                "nodes": normalized_nodes if nodes_changed else state.nodes,
            }
        )
        normalized_refs = refs.model_copy(
            update={
                "source_session_key": self._normalize_optional_session_key(refs.source_session_key, agent_id),
                "root_session_key": self._normalize_optional_session_key(refs.root_session_key, agent_id),
                "planner_session_key": self._normalize_optional_session_key(refs.planner_session_key, agent_id),
                "driver_session_key": self._normalize_optional_session_key(refs.driver_session_key, agent_id),
                "node_sessions": {
                    node_id: self._effective_session_key(session_key, agent_id)
                    for node_id, session_key in refs.node_sessions.items()
                },
            }
        )
        return normalized_state, normalized_refs

    def _effective_session_key(self, session_key: str, agent_id: str) -> str:
        return qualify_agent_session_key(session_key, agent_id)

    def _normalize_optional_session_key(self, session_key: str | None, agent_id: str) -> str | None:
        if not session_key:
            return None
        return self._effective_session_key(session_key, agent_id)

    def _run_dir_rel(self, run_id: str) -> str:
        return Path("runs", run_id).as_posix()

    async def _publish(self, state: RunState) -> None:
        payload = state.model_dump(by_alias=True, exclude_none=True)
        for queue in list(self._subscribers[state.run_id]):
            await queue.put(payload)
