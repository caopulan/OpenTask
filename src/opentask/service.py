from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .config import get_settings
from .models import CreateRunRequest, NodeState, OpenClawRefs, RunEvent, RunState, WorkflowNode, utc_now
from .openclaw_client import OpenClawClient
from .store import RunStore
from .workflow import (
    build_starter_workflow,
    ensure_summary_node,
    load_workflow,
    parse_workflow_markdown,
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

    async def wait_run(self, run_id: str, timeout_ms: int) -> dict: ...

    async def cron_add(self, params: dict) -> dict: ...

    async def cron_update(self, job_id: str, patch: dict) -> dict: ...

    async def cron_run(self, job_id: str) -> dict: ...

    async def chat_history(self, session_key: str, limit: int = 20) -> list[dict]: ...


TERMINAL_STATUSES = {"completed", "failed", "skipped"}


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
        self.gateway = gateway or OpenClawClient()
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = defaultdict(set)

    def list_runs(self) -> list[RunState]:
        return self.store.list_runs()

    def get_run(self, run_id: str) -> RunState:
        return self.store.load_state(run_id)

    def get_events(self, run_id: str, limit: int | None = None) -> list[RunEvent]:
        return self.store.load_events(run_id, limit=limit)

    async def create_run(self, request: CreateRunRequest) -> RunState:
        parsed = self._resolve_workflow(request)
        parsed, added_events = ensure_summary_node(parsed)
        state, refs = self.store.create_run(parsed)

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
        state = await self.tick_run(state.run_id)
        return state

    async def tick_run(self, run_id: str) -> RunState:
        workflow = self.store.load_workflow_lock(run_id)
        state = self.store.load_state(run_id)
        refs = self.store.load_openclaw_refs(run_id)

        if state.status in {"paused", "completed", "cancelled"}:
            return state

        state = await self._sync_running_nodes(state)
        state = self._advance_waiting_nodes(state)
        state = self._promote_ready_nodes(state)
        state = await self._dispatch_ready_nodes(state, workflow.definition.nodes, refs)
        state = await self._finalize_if_terminal(state)
        self.store.write_state(state)
        await self._publish(state)
        return state

    async def pause_run(self, run_id: str) -> RunState:
        state = self.store.load_state(run_id)
        refs = self.store.load_openclaw_refs(run_id)
        if refs.cron_job_id:
            await self.gateway.cron_update(refs.cron_job_id, {"enabled": False})
        state = self.store.update_state_timestamp(
            state.model_copy(update={"status": "paused"}),
            last_event="run.paused",
        )
        self.store.write_state(state)
        self.store.append_event(run_id, RunEvent(event="run.paused", runId=run_id))
        await self._publish(state)
        return state

    async def resume_run(self, run_id: str) -> RunState:
        state = self.store.load_state(run_id)
        refs = self.store.load_openclaw_refs(run_id)
        if refs.cron_job_id:
            await self.gateway.cron_update(refs.cron_job_id, {"enabled": True})
        state = self.store.update_state_timestamp(
            state.model_copy(update={"status": "running"}),
            last_event="run.resumed",
        )
        self.store.write_state(state)
        self.store.append_event(run_id, RunEvent(event="run.resumed", runId=run_id))
        await self._publish(state)
        return state

    async def retry_node(self, run_id: str, node_id: str) -> RunState:
        state = self.store.load_state(run_id)
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
                            "notes": [*node.notes, "Retried by operator."],
                        }
                    )
                )
            else:
                nodes.append(node)
        state = self.store.update_state_timestamp(
            state.model_copy(update={"status": "running", "nodes": nodes}),
            last_event="node.retry",
        )
        self.store.write_state(state)
        self.store.append_event(
            run_id,
            RunEvent(event="node.ready", runId=run_id, nodeId=node_id, message="Node retried."),
        )
        return await self.tick_run(run_id)

    async def skip_node(self, run_id: str, node_id: str) -> RunState:
        state = self.store.load_state(run_id)
        nodes = []
        for node in state.nodes:
            if node.id == node_id:
                nodes.append(
                    node.model_copy(
                        update={
                            "status": "skipped",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, "Skipped by operator."],
                        }
                    )
                )
            else:
                nodes.append(node)
        state = self.store.update_state_timestamp(
            state.model_copy(update={"nodes": nodes}),
            last_event="node.skipped",
        )
        self.store.write_state(state)
        self.store.append_event(
            run_id,
            RunEvent(event="node.skipped", runId=run_id, nodeId=node_id, message="Node skipped."),
        )
        return await self.tick_run(run_id)

    async def approve_node(self, run_id: str, node_id: str) -> RunState:
        state = self.store.load_state(run_id)
        nodes = []
        for node in state.nodes:
            if node.id == node_id:
                nodes.append(
                    node.model_copy(
                        update={
                            "status": "completed",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, "Approved by operator."],
                        }
                    )
                )
            else:
                nodes.append(node)
        state = self.store.update_state_timestamp(
            state.model_copy(update={"nodes": nodes}),
            last_event="node.approved",
        )
        self.store.write_state(state)
        self.store.append_event(
            run_id,
            RunEvent(
                event="node.completed",
                runId=run_id,
                nodeId=node_id,
                message="Approval gate completed by operator.",
            ),
        )
        return await self.tick_run(run_id)

    async def force_tick(self, run_id: str) -> RunState:
        refs = self.store.load_openclaw_refs(run_id)
        if refs.cron_job_id:
            await self.gateway.cron_run(refs.cron_job_id)
        return await self.tick_run(run_id)

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
                candidate = self.project_root / candidate
            return load_workflow(candidate)
        if request.task_text:
            title = request.title or "OpenTask run"
            return build_starter_workflow(title, request.task_text)
        raise ValueError("one of workflowPath, workflowMarkdown, or taskText is required")

    async def _bootstrap_openclaw(
        self,
        state: RunState,
        refs: OpenClawRefs,
        parsed,
        planner_prompt: str,
        driver_prompt: str,
    ) -> RunState:
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
        self.store.write_openclaw_refs(state.run_id, refs)
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
                updated_nodes.append(
                    node.model_copy(
                        update={
                            "status": "completed",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, "Completed by OpenClaw run."],
                            "artifact_paths": self._artifact_paths_after_report(state.run_id, node, result),
                        }
                    )
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
                updated_nodes.append(
                    node.model_copy(
                        update={
                            "status": "failed",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, json.dumps(result, ensure_ascii=True)],
                        }
                    )
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
                updated_nodes.append(
                    node.model_copy(
                        update={
                            "status": "completed",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, "next_tick condition satisfied."],
                        }
                    )
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
                updated_nodes.append(
                    node.model_copy(
                        update={
                            "status": "completed",
                            "completed_at": utc_now(),
                            "notes": [*node.notes, f"Detected file {wait_for.path}."],
                        }
                    )
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
        workflow_nodes: list[WorkflowNode],
        refs: OpenClawRefs,
    ) -> RunState:
        definitions = {node.id: node for node in workflow_nodes}
        changed = False
        updated_nodes: list[NodeState] = []

        for node in state.nodes:
            if node.status != "ready":
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
                updated_nodes.append(
                    node.model_copy(
                        update={
                            "status": "completed",
                            "completed_at": utc_now(),
                            "artifact_paths": [*node.artifact_paths, report_path],
                        }
                    )
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

            session_key = definition.session_key or self._session_key_for_node(state.run_id, node.id, node.kind)
            run_id = f"{state.run_id}-{node.id}-{uuid4().hex[:8]}"
            response = await self.gateway.send_chat(
                session_key=session_key,
                message=definition.prompt,
                idempotency_key=run_id,
                timeout_ms=definition.timeout_ms or self.settings.default_tick_timeout_ms,
            )
            gateway_status = response.get("status")
            payload_update = {
                "status": "running" if gateway_status in {None, "accepted", "started", "timeout"} else "completed",
                "started_at": utc_now(),
                "run_id": str(response.get("runId") or response.get("id") or run_id),
                "child_session_key" if node.kind == "subagent" else "session_key": session_key,
            }
            updated = node.model_copy(update=payload_update)
            refs.node_run_ids[node.id] = updated.run_id or run_id
            if node.kind == "subagent":
                refs.child_sessions[node.id] = session_key
            else:
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
                updated_nodes[-1] = updated.model_copy(
                    update={
                        "status": "completed",
                        "completed_at": utc_now(),
                        "artifact_paths": self._artifact_paths_after_report(state.run_id, updated, response),
                    }
                )

        if not changed:
            return state
        self.store.write_openclaw_refs(state.run_id, refs)
        return self.store.update_state_timestamp(
            state.model_copy(update={"nodes": updated_nodes}),
            last_event="node.started",
        )

    async def _finalize_if_terminal(self, state: RunState) -> RunState:
        statuses = {node.status for node in state.nodes}
        if not statuses.issubset(TERMINAL_STATUSES):
            return state

        refs = self.store.load_openclaw_refs(state.run_id)
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

    def _artifact_paths_after_report(self, run_id: str, node: NodeState, payload: dict) -> list[str]:
        if node.outputs_mode != "report":
            return node.artifact_paths
        report = "\n".join(
            [
                f"# {node.title}",
                "",
                f"- Status: {payload.get('status', 'ok')}",
                f"- Session: {node.session_key or node.child_session_key or 'n/a'}",
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

    def _build_planner_prompt(self, run_id: str, body: str) -> str:
        return (
            f"You are the planner session for OpenTask run {run_id}.\n"
            "Read workflow.lock.md and keep the human-readable objective in mind.\n"
            "Do not overwrite the workflow file; use it as the frozen plan for execution.\n\n"
            f"{body}".strip()
        )

    def _build_driver_prompt(self, run_id: str) -> str:
        return (
            f"You are the idempotent driver for OpenTask run {run_id}.\n"
            "On each tick, read workflow.lock.md, state.json, and nodes/* artifacts.\n"
            "Never repeat completed nodes. Advance only ready nodes, inspect running nodes, and record all mutations in events.jsonl."
        )

    def _session_key_for_node(self, run_id: str, node_id: str, kind: str) -> str:
        suffix = "subagent" if kind == "subagent" else "node"
        return f"session:workflow:{run_id}:{suffix}:{node_id}"

    async def _publish(self, state: RunState) -> None:
        payload = state.model_dump(by_alias=True, exclude_none=True)
        for queue in list(self._subscribers[state.run_id]):
            await queue.put(payload)
