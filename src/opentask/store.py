from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from secrets import token_hex

from .config import get_settings
from .models import (
    DeliveryContext,
    NodeResult,
    NodeState,
    NodeWorkingMemory,
    ParsedWorkflow,
    RunControlAction,
    RunEvent,
    RunNodeDocument,
    RunRefs,
    RunState,
    utc_now,
)
from .session_keys import render_agent_session_key
from .workflow import ensure_relative_paths, normalize_artifact_paths, render_workflow_markdown


class RunStore:
    _DOCUMENT_PREVIEW_BYTES = 12_000

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
            node_state = NodeState(
                id=node.id,
                title=node.title,
                kind=node.kind,
                status=status,
                needs=node.needs,
                outputsMode=node.outputs.mode,
                artifactPaths=artifact_paths,
                workingMemory=self.node_working_memory_paths(node.id, node.kind),
                waitFor=node.wait_for,
            )
            self.ensure_node_runtime_files(run_id, node_state)
            nodes.append(node_state)

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

    def load_node_documents(self, run_id: str, node_id: str) -> list[RunNodeDocument]:
        state = self.load_state(run_id)
        node = next((candidate for candidate in state.nodes if candidate.id == node_id), None)
        if node is None:
            raise FileNotFoundError(f"node not found: {node_id}")

        documents: list[RunNodeDocument] = []
        seen_paths: set[str] = set()
        for category, path in self._iter_node_document_paths(node):
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            resolved = self._resolve_run_relative_path(run_id, path)
            if not resolved.exists() or not resolved.is_file() or not self._is_previewable_text_file(resolved):
                continue
            content, format_name, truncated = self._read_document_preview(resolved)
            documents.append(
                RunNodeDocument(
                    path=path,
                    label=self._document_label(path, category),
                    category=category,
                    format=format_name,
                    content=content,
                    truncated=truncated,
                )
            )
        return documents

    def write_node_report(self, run_id: str, node_id: str, filename: str, content: str) -> str:
        return self.write_node_file(run_id, node_id, filename, content)

    def write_node_file(self, run_id: str, node_id: str, filename: str, content: str) -> str:
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

    def node_working_memory_paths(self, node_id: str, kind: str) -> NodeWorkingMemory | None:
        if kind not in {"session_turn", "subagent", "summary"}:
            return None
        return NodeWorkingMemory(
            plan=f"nodes/{node_id}/plan.md",
            findings=f"nodes/{node_id}/findings.md",
            progress=f"nodes/{node_id}/progress.md",
            handoff=f"nodes/{node_id}/handoff.md" if kind == "subagent" else None,
        )

    def ensure_node_runtime_files(self, run_id: str, node: NodeState) -> None:
        node_dir = self._run_dir(run_id) / "nodes" / node.id
        node_dir.mkdir(parents=True, exist_ok=True)
        if node.working_memory is None:
            return
        self._write_file_if_missing(
            self._run_dir(run_id) / node.working_memory.plan,
            self._default_node_plan(node),
        )
        self._write_file_if_missing(
            self._run_dir(run_id) / node.working_memory.findings,
            self._default_node_findings(node),
        )
        self._write_file_if_missing(
            self._run_dir(run_id) / node.working_memory.progress,
            self._default_node_progress(node),
        )
        if node.working_memory.handoff:
            self._write_file_if_missing(
                self._run_dir(run_id) / node.working_memory.handoff,
                self._default_node_handoff(node),
            )

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

    def _resolve_run_relative_path(self, run_id: str, relative_path: str) -> Path:
        run_dir = self._run_dir(run_id).resolve()
        resolved = (run_dir / relative_path).resolve()
        if run_dir not in resolved.parents and resolved != run_dir:
            raise ValueError(f"path escapes run directory: {relative_path}")
        return resolved

    @classmethod
    def _read_document_preview(cls, path: Path) -> tuple[str, str, bool]:
        format_name = "json" if path.suffix == ".json" else "markdown" if path.suffix == ".md" else "text"
        text = path.read_text(encoding="utf-8")
        if format_name == "json":
            payload = json.loads(text)
            text = json.dumps(payload, indent=2, ensure_ascii=False)
        truncated = len(text.encode("utf-8")) > cls._DOCUMENT_PREVIEW_BYTES
        if truncated:
            text = text[: cls._DOCUMENT_PREVIEW_BYTES]
        return text, format_name, truncated

    @staticmethod
    def _iter_node_document_paths(node: NodeState) -> list[tuple[str, str]]:
        paths: list[tuple[str, str]] = []
        for path in node.artifact_paths:
            paths.append(("artifact", path))
        if node.working_memory is not None:
            for path in (
                node.working_memory.findings,
                node.working_memory.progress,
                node.working_memory.plan,
                node.working_memory.handoff,
            ):
                if path:
                    paths.append(("working_memory", path))
        priorities = {
            "report.md": 0,
            "nodes/summary/report.md": 1,
            "findings.md": 2,
            "progress.md": 3,
            "plan.md": 4,
            "result.json": 5,
            "handoff.md": 6,
        }

        def sort_key(item: tuple[str, str]) -> tuple[int, str]:
            _, path = item
            name = Path(path).name
            if path == "nodes/summary/report.md":
                return priorities["nodes/summary/report.md"], path
            return priorities.get(name, 99), path

        return sorted(paths, key=sort_key)

    @staticmethod
    def _document_label(path: str, category: str) -> str:
        if path == "nodes/summary/report.md":
            return "Summary"
        name = Path(path).name
        if name == "report.md":
            return "Report"
        if name == "findings.md":
            return "Findings"
        if name == "progress.md":
            return "Progress"
        if name == "plan.md":
            return "Plan"
        if name == "handoff.md":
            return "Handoff"
        if name == "result.json":
            return "Result"
        return "Artifact" if category == "artifact" else "Plan"

    @staticmethod
    def _is_previewable_text_file(path: Path) -> bool:
        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type and not (mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"}):
            return False
        try:
            sample = path.read_bytes()[:1024]
        except OSError:
            return False
        if b"\x00" in sample:
            return False
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True

    @staticmethod
    def _write_file_if_missing(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _default_node_plan(node: NodeState) -> str:
        return (
            f"# {node.title} plan\n\n"
            f"- Node ID: `{node.id}`\n"
            f"- Kind: `{node.kind}`\n"
            f"- Status: `{node.status}`\n\n"
            "Use this file only if this node expands into multiple concrete steps.\n"
            "Keep the plan scoped to this node; do not duplicate the global workflow here.\n"
        )

    @staticmethod
    def _default_node_findings(node: NodeState) -> str:
        return (
            f"# {node.title} findings\n\n"
            "Record node-local discoveries, source links, and intermediate conclusions here.\n"
        )

    @staticmethod
    def _default_node_progress(node: NodeState) -> str:
        return (
            f"# {node.title} progress\n\n"
            "Append concise node-local execution updates here when the node spans multiple steps.\n"
        )

    @staticmethod
    def _default_node_handoff(node: NodeState) -> str:
        return (
            f"# {node.title} handoff\n\n"
            "The parent orchestrator can place the concrete child brief for this node here before dispatch.\n"
        )

    @staticmethod
    def _read_json(path: Path, model_type):
        payload = json.loads(path.read_text(encoding="utf-8"))
        return model_type.model_validate(payload)
