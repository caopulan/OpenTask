from __future__ import annotations

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
    assert (run_dir / "nodes" / "execute-task" / "plan.md").exists()
    assert (run_dir / "nodes" / "execute-task" / "findings.md").exists()
    assert (run_dir / "nodes" / "execute-task" / "progress.md").exists()
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
