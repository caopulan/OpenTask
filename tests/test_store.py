from __future__ import annotations

import json
from pathlib import Path

from opentask.store import RunStore
from opentask.workflow import build_starter_workflow


def test_run_store_creates_expected_files(tmp_path: Path) -> None:
    store = RunStore(runtime_root=tmp_path / ".opentask")
    workflow = build_starter_workflow("Store demo", "Run the task")

    state, refs = store.create_run(workflow)

    run_dir = tmp_path / ".opentask" / "runs" / state.run_id
    assert (run_dir / "workflow.lock.md").exists()
    assert (run_dir / "state.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "refs.json").exists()
    assert (run_dir / "control.jsonl").exists()
    assert (run_dir / "nodes" / "execute-task").exists()
    assert refs.driver_session_key.startswith("agent:opentask:session:workflow:")
    assert refs.driver_session_key.endswith(":root")
    assert state.planner_session_key.startswith("agent:opentask:session:workflow:")
    assert state.root_session_key == refs.root_session_key
    assert state.nodes[0].status == "ready"
    assert state.nodes[0].working_memory is not None
    assert state.nodes[0].working_memory.plan == "nodes/execute-task/plan.md"


def test_append_and_load_events(tmp_path: Path) -> None:
    store = RunStore(runtime_root=tmp_path / ".opentask")
    workflow = build_starter_workflow("Events", "Track events")
    state, _ = store.create_run(workflow)

    store.write_node_report(state.run_id, "execute-task", "report.md", "# Report")
    events = store.load_events(state.run_id)

    assert events[0].event == "run.created"


def test_load_node_documents_reads_declared_text_files_only(tmp_path: Path) -> None:
    store = RunStore(runtime_root=tmp_path / ".opentask")
    workflow = build_starter_workflow("Documents", "Preview outputs")
    state, _ = store.create_run(workflow)
    state = state.model_copy(
        update={
            "nodes": [
                node.model_copy(update={"artifact_paths": [*node.artifact_paths, "nodes/execute-task/result.json"]})
                if node.id == "execute-task"
                else node
                for node in state.nodes
            ]
        }
    )
    store.write_state(state)

    store.write_node_report(state.run_id, "execute-task", "report.md", "# Report\n\nhello")
    store.write_node_file(state.run_id, "execute-task", "result.json", json.dumps({"status": "ok"}))

    documents = store.load_node_documents(state.run_id, "execute-task")

    assert [document.label for document in documents] == ["Report", "Result"]
    assert next(document for document in documents if document.label == "Report").format == "markdown"
    assert next(document for document in documents if document.label == "Result").content.startswith("{\n  ")


def test_load_node_documents_omits_placeholder_working_memory(tmp_path: Path) -> None:
    store = RunStore(runtime_root=tmp_path / ".opentask")
    workflow = build_starter_workflow("Placeholders", "Preview outputs")
    state, _ = store.create_run(workflow)
    node = state.nodes[0]

    store.write_node_file(state.run_id, node.id, "plan.md", store._default_node_plan(node))
    store.write_node_file(state.run_id, node.id, "findings.md", store._default_node_findings(node))
    store.write_node_file(state.run_id, node.id, "progress.md", store._default_node_progress(node))

    assert store.load_node_documents(state.run_id, node.id) == []
