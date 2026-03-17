from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "skills" / "opentask" / "scripts" / "registry_helper.py"


def run_helper(*args: str, expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(HELPER), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if expect_ok and completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    if not expect_ok and completed.returncode == 0:
        raise AssertionError("command unexpectedly succeeded")
    return completed


def write_demo_workflow(root: Path) -> tuple[Path, Path]:
    workflow_path = root / "workflows" / "demo.task.md"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        """---
workflowId: demo
title: Demo workflow
defaults:
  agentId: main
driver:
  cron: "*/5 * * * *"
nodes:
  - id: gather-context
    title: Gather context
    kind: session_turn
    needs: []
    prompt: Gather context.
    outputs:
      mode: report
      requiredFiles:
        - nodes/gather-context/report.md
        - nodes/gather-context/result.json
  - id: summary
    title: Summary
    kind: summary
    needs:
      - gather-context
    prompt: Summarize.
    outputs:
      mode: report
      requiredFiles:
        - nodes/summary/report.md
        - nodes/summary/result.json
---
""",
        encoding="utf-8",
    )
    spec_path = root / "workflow-spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "workflowId": "demo",
                "title": "Demo workflow",
                "defaults": {"agentId": "main"},
                "nodes": [
                    {
                        "id": "gather-context",
                        "title": "Gather context",
                        "kind": "session_turn",
                        "needs": [],
                        "outputs": {
                            "mode": "report",
                            "requiredFiles": [
                                "nodes/gather-context/report.md",
                                "nodes/gather-context/result.json",
                            ],
                        },
                    },
                    {
                        "id": "summary",
                        "title": "Summary",
                        "kind": "summary",
                        "needs": ["gather-context"],
                        "outputs": {
                            "mode": "report",
                            "requiredFiles": [
                                "nodes/summary/report.md",
                                "nodes/summary/result.json",
                            ],
                        },
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return workflow_path, spec_path


def test_registry_helper_scaffold_and_transitions(tmp_path: Path) -> None:
    workflow_path, spec_path = write_demo_workflow(tmp_path)

    run_helper(
        "--registry-root",
        str(tmp_path),
        "scaffold",
        "--workflow-path",
        str(workflow_path.relative_to(tmp_path)),
        "--run-id",
        "demo-001",
        "--source-session-key",
        "agent:main:discord:channel:123",
        "--source-agent-id",
        "main",
        "--delivery-context-json",
        json.dumps({"channel": "discord", "to": "channel:123"}),
    )

    run_dir = tmp_path / "runs" / "demo-001"
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["nodes"][0]["status"] == "ready"
    assert state["nodes"][1]["status"] == "pending"
    assert (run_dir / "nodes" / "gather-context" / "plan.md").exists()
    assert (run_dir / "control.jsonl").read_text(encoding="utf-8") == ""

    run_helper(
        "--registry-root",
        str(tmp_path),
        "bind",
        "demo-001",
        "node-session",
        "--node-id",
        "gather-context",
        "--value",
        "agent:main:session:workflow:demo-001:gather-context",
    )
    run_helper(
        "--registry-root",
        str(tmp_path),
        "bind",
        "demo-001",
        "cron",
        "--value",
        "cron-demo-001",
    )
    run_helper(
        "--registry-root",
        str(tmp_path),
        "transition-node",
        "demo-001",
        "gather-context",
        "running",
    )
    run_helper(
        "--registry-root",
        str(tmp_path),
        "transition-node",
        "demo-001",
        "gather-context",
        "completed",
    )
    run_helper(
        "--registry-root",
        str(tmp_path),
        "transition-node",
        "demo-001",
        "summary",
        "running",
    )
    run_helper(
        "--registry-root",
        str(tmp_path),
        "transition-node",
        "demo-001",
        "summary",
        "completed",
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    refs = json.loads((run_dir / "refs.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    assert state["status"] == "completed"
    assert refs["cronJobId"] == "cron-demo-001"
    assert refs["nodeSessions"]["gather-context"].endswith(":gather-context")
    assert any(event["event"] == "node.ready" and event.get("nodeId") == "summary" for event in events)
    assert events[-1]["event"] == "run.completed"

    validate = run_helper("--registry-root", str(tmp_path), "validate", "demo-001")
    payload = json.loads(validate.stdout)
    assert payload["ok"] is True


def test_registry_helper_supports_explicit_spec_file(tmp_path: Path) -> None:
    workflow_path, spec_path = write_demo_workflow(tmp_path)
    run_helper(
        "--registry-root",
        str(tmp_path),
        "scaffold",
        "--workflow-path",
        str(workflow_path.relative_to(tmp_path)),
        "--spec-file",
        str(spec_path),
        "--run-id",
        "demo-spec-001",
        "--source-session-key",
        "agent:main:discord:channel:999",
        "--source-agent-id",
        "main",
    )

    run_dir = tmp_path / "runs" / "demo-spec-001"
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["workflowId"] == "demo"
    assert state["nodes"][0]["id"] == "gather-context"


def test_registry_helper_validate_detects_inconsistent_run_state(tmp_path: Path) -> None:
    workflow_path, spec_path = write_demo_workflow(tmp_path)
    run_helper(
        "--registry-root",
        str(tmp_path),
        "scaffold",
        "--workflow-path",
        str(workflow_path.relative_to(tmp_path)),
        "--spec-file",
        str(spec_path),
        "--run-id",
        "demo-002",
        "--source-session-key",
        "agent:main:discord:channel:456",
        "--source-agent-id",
        "main",
    )
    run_dir = tmp_path / "runs" / "demo-002"
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    for node in state["nodes"]:
        node["status"] = "completed"
        node["startedAt"] = "2026-03-17T00:00:00+00:00"
        node["completedAt"] = "2026-03-17T00:00:01+00:00"
    state["status"] = "running"
    (run_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    completed = run_helper("--registry-root", str(tmp_path), "validate", "demo-002", expect_ok=False)
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert "run has all terminal nodes but state.status is not terminal" in payload["issues"]
