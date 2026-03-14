from __future__ import annotations

import json
from pathlib import Path
from secrets import token_hex

from .config import get_settings
from .models import NodeState, OpenClawRefs, ParsedWorkflow, RunEvent, RunState, utc_now
from .workflow import ensure_relative_paths, normalize_artifact_paths, render_workflow_markdown


class RunStore:
    def __init__(self, runtime_root: Path | None = None) -> None:
        settings = get_settings()
        self.runtime_root = runtime_root or settings.runtime_root
        self.runs_root = self.runtime_root / "runs"
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def list_runs(self) -> list[RunState]:
        runs: list[RunState] = []
        if not self.runs_root.exists():
            return runs
        for state_file in sorted(self.runs_root.glob("*/state.json")):
            runs.append(self._read_json(state_file, RunState))
        return sorted(runs, key=lambda item: item.updated_at, reverse=True)

    def create_run(self, workflow: ParsedWorkflow) -> tuple[RunState, OpenClawRefs]:
        run_id = self._next_run_id()
        run_dir = self._run_dir(run_id)
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

        state = RunState(
            runId=run_id,
            workflowId=workflow.definition.workflow_id,
            title=workflow.definition.title,
            status="running",
            plannerSessionKey=workflow.definition.driver.planner_session_key_template.format(run_id=run_id),
            driverSessionKey=workflow.definition.driver.session_key_template.format(run_id=run_id),
            nodes=nodes,
            lastEvent="run.created",
        )
        refs = OpenClawRefs(
            plannerSessionKey=state.planner_session_key,
            driverSessionKey=state.driver_session_key,
        )

        self.write_workflow_lock(run_id, workflow)
        self.write_state(state)
        self.write_openclaw_refs(run_id, refs)
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

    def load_openclaw_refs(self, run_id: str) -> OpenClawRefs:
        return self._read_json(self._run_dir(run_id) / "openclaw.json", OpenClawRefs)

    def write_openclaw_refs(self, run_id: str, refs: OpenClawRefs) -> None:
        self._write_json(
            self._run_dir(run_id) / "openclaw.json",
            refs.model_dump(by_alias=True, exclude_none=True),
        )

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

    def write_node_report(self, run_id: str, node_id: str, filename: str, content: str) -> str:
        path = self._run_dir(run_id) / "nodes" / node_id / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
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
