from __future__ import annotations

import json
from pathlib import Path
from secrets import token_hex

from .config import get_settings
from .models import (
    DeliveryContext,
    NodeResult,
    NodeState,
    ParsedWorkflow,
    RunControlAction,
    RunEvent,
    RunRefs,
    RunState,
    utc_now,
)
from .session_keys import render_agent_session_key
from .workflow import ensure_relative_paths, normalize_artifact_paths, render_workflow_markdown


class RunStore:
    def __init__(
        self,
        registry_root: Path | None = None,
        *,
        runtime_root: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.registry_root = registry_root or runtime_root or settings.registry_root
        self.runtime_root = self.registry_root
        self.runs_root = self.registry_root / "runs"
        self.workflows_root = self.registry_root / "workflows"
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.workflows_root.mkdir(parents=True, exist_ok=True)

    def list_runs(self) -> list[RunState]:
        runs: list[RunState] = []
        if not self.runs_root.exists():
            return runs
        for state_file in sorted(self.runs_root.glob("*/state.json")):
            runs.append(self._read_json(state_file, RunState))
        return sorted(runs, key=lambda item: item.updated_at, reverse=True)

    def next_run_id(self) -> str:
        return self._next_run_id()

    def create_run(
        self,
        workflow: ParsedWorkflow,
        *,
        run_id: str | None = None,
        source_session_key: str | None = None,
        source_agent_id: str | None = None,
        delivery_context: DeliveryContext | None = None,
        root_session_key: str | None = None,
    ) -> tuple[RunState, RunRefs]:
        run_id = run_id or self.next_run_id()
        run_dir = self._run_dir(run_id)
        if (run_dir / "state.json").exists():
            raise FileExistsError(f"run already exists: {run_id}")
        (run_dir / "nodes").mkdir(parents=True, exist_ok=True)

        nodes: list[NodeState] = []
        for node in workflow.definition.nodes:
            artifact_paths = ensure_relative_paths(normalize_artifact_paths(node))
            status = "ready" if not node.needs else "pending"
            node_dir = run_dir / "nodes" / node.id
            node_dir.mkdir(parents=True, exist_ok=True)
            nodes.append(
                NodeState(
                    id=node.id,
                    title=node.title,
                    kind=node.kind,
                    status=status,
                    needs=node.needs,
                    outputsMode=node.outputs.mode,
                    artifactPaths=artifact_paths,
                    waitFor=node.wait_for,
                )
            )

        resolved_root_session_key = root_session_key or source_session_key or render_agent_session_key(
            "session:workflow:{run_id}:root",
            run_id=run_id,
            agent_id=workflow.definition.defaults.agent_id,
        )
        state = RunState(
            runId=run_id,
            workflowId=workflow.definition.workflow_id,
            title=workflow.definition.title,
            status="running",
            sourceSessionKey=source_session_key,
            sourceAgentId=source_agent_id,
            deliveryContext=delivery_context,
            rootSessionKey=resolved_root_session_key,
            plannerSessionKey=resolved_root_session_key,
            driverSessionKey=resolved_root_session_key,
            nodes=nodes,
            lastEvent="run.created",
        )
        refs = RunRefs(
            runId=run_id,
            sourceSessionKey=source_session_key,
            sourceAgentId=source_agent_id,
            deliveryContext=delivery_context,
            rootSessionKey=resolved_root_session_key,
            plannerSessionKey=state.planner_session_key,
            driverSessionKey=state.driver_session_key,
        )

        self.write_workflow_lock(run_id, workflow)
        self.write_state(state)
        self.write_run_refs(run_id, refs)
        (run_dir / "control.jsonl").touch()
        self.append_event(
            run_id,
            RunEvent(
                event="run.created",
                runId=run_id,
                message="Created run directory and initialized state projection.",
            ),
        )
        return state, refs

    def write_workflow_lock(self, run_id: str, workflow: ParsedWorkflow) -> None:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "workflow.lock.md"
        path.write_text(render_workflow_markdown(workflow), encoding="utf-8")

    def load_workflow_lock(self, run_id: str) -> ParsedWorkflow:
        from .workflow import parse_workflow_markdown

        path = self._run_dir(run_id) / "workflow.lock.md"
        return parse_workflow_markdown(path.read_text(encoding="utf-8"), source_path=str(path))

    def load_state(self, run_id: str) -> RunState:
        return self._read_json(self._run_dir(run_id) / "state.json", RunState)

    def write_state(self, state: RunState) -> None:
        path = self._run_dir(state.run_id) / "state.json"
        self._write_json(path, state.model_dump(by_alias=True, exclude_none=True))

    def load_run_refs(self, run_id: str) -> RunRefs:
        run_dir = self._run_dir(run_id)
        refs_path = run_dir / "refs.json"
        if refs_path.exists():
            return self._read_json(refs_path, RunRefs)
        return self._read_json(run_dir / "openclaw.json", RunRefs)

    def write_run_refs(self, run_id: str, refs: RunRefs) -> None:
        self._write_json(self._run_dir(run_id) / "refs.json", refs.model_dump(by_alias=True, exclude_none=True))

    def load_openclaw_refs(self, run_id: str) -> RunRefs:
        return self.load_run_refs(run_id)

    def write_openclaw_refs(self, run_id: str, refs: RunRefs) -> None:
        self.write_run_refs(run_id, refs)

    def append_event(self, run_id: str, event: RunEvent) -> None:
        path = self._run_dir(run_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(by_alias=True, exclude_none=True), ensure_ascii=True))
            handle.write("\n")

    def load_events(self, run_id: str, limit: int | None = None) -> list[RunEvent]:
        path = self._run_dir(run_id) / "events.jsonl"
        if not path.exists():
            return []
        events = [
            RunEvent.model_validate(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if limit is not None and limit >= 0:
            return events[-limit:]
        return events

    def append_control_action(self, run_id: str, action: RunControlAction) -> None:
        path = self._run_dir(run_id) / "control.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(action.model_dump(by_alias=True, exclude_none=True), ensure_ascii=True))
            handle.write("\n")

    def load_control_actions(self, run_id: str, limit: int | None = None) -> list[RunControlAction]:
        path = self._run_dir(run_id) / "control.jsonl"
        if not path.exists():
            return []
        actions = [
            RunControlAction.model_validate(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if limit is not None and limit >= 0:
            return actions[-limit:]
        return actions

    def write_node_report(self, run_id: str, node_id: str, filename: str, content: str) -> str:
        path = self._run_dir(run_id) / "nodes" / node_id / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self._run_dir(run_id)))

    def write_node_result(self, run_id: str, node_id: str, result: NodeResult) -> str:
        path = self._run_dir(run_id) / "nodes" / node_id / "result.json"
        self._write_json(path, result.model_dump(by_alias=True, exclude_none=True))
        return str(path.relative_to(self._run_dir(run_id)))

    def write_support_file(self, run_id: str, filename: str, content: str) -> str:
        path = self._run_dir(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self._run_dir(run_id)))

    def update_state_timestamp(self, state: RunState, *, last_event: str) -> RunState:
        return state.model_copy(
            update={
                "updated_at": utc_now(),
                "last_event": last_event,
            }
        )

    def _run_dir(self, run_id: str) -> Path:
        return self.runs_root / run_id

    def _next_run_id(self) -> str:
        return f"{Path.cwd().name.lower()}-{token_hex(4)}"

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    @staticmethod
    def _read_json(path: Path, model_type):
        payload = json.loads(path.read_text(encoding="utf-8"))
        return model_type.model_validate(payload)
