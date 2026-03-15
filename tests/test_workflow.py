from __future__ import annotations

import pytest

from opentask.workflow import (
    WorkflowValidationError,
    build_starter_workflow,
    ensure_summary_node,
    parse_workflow_markdown,
)


def test_parse_valid_workflow() -> None:
    parsed = parse_workflow_markdown(
        """---
workflowId: sample
title: Sample workflow
nodes:
  - id: first
    title: First node
    kind: session_turn
    needs: []
    prompt: Do the first thing.
    outputs:
      mode: report
---

# Sample
"""
    )

    assert parsed.definition.workflow_id == "sample"
    assert parsed.definition.nodes[0].id == "first"


@pytest.mark.parametrize(
    ("markdown", "message"),
    [
        (
            """---
workflowId: dupes
title: Duplicate ids
nodes:
  - id: same
    title: A
    kind: session_turn
    needs: []
    prompt: A
    outputs: {mode: report}
  - id: same
    title: B
    kind: session_turn
    needs: []
    prompt: B
    outputs: {mode: report}
---
""",
            "duplicate node ids",
        ),
        (
            """---
workflowId: missing-needs
title: Missing dependency
nodes:
  - id: first
    title: First
    kind: session_turn
    needs: [ghost]
    prompt: A
    outputs: {mode: report}
---
""",
            "missing node dependencies",
        ),
        (
            """---
workflowId: cycle
title: Cycle
nodes:
  - id: one
    title: One
    kind: session_turn
    needs: [two]
    prompt: A
    outputs: {mode: report}
  - id: two
    title: Two
    kind: session_turn
    needs: [one]
    prompt: B
    outputs: {mode: report}
---
""",
            "dependency cycles",
        ),
    ],
)
def test_invalid_graphs_raise(markdown: str, message: str) -> None:
    with pytest.raises(WorkflowValidationError, match=message):
        parse_workflow_markdown(markdown)


def test_ensure_summary_node_adds_terminal_summary() -> None:
    parsed = build_starter_workflow("Starter", "Finish the task")
    summary = parsed.definition.nodes[-1]

    assert parsed.definition.defaults.agent_id == "opentask"
    assert summary.kind == "summary"
    assert summary.needs == ["execute-task"]


def test_wait_node_requires_path_for_file_exists() -> None:
    with pytest.raises(ValueError, match="waitFor.path"):
        parse_workflow_markdown(
            """---
workflowId: wait-demo
title: Wait demo
nodes:
  - id: wait
    title: Wait
    kind: wait
    needs: []
    prompt: ""
    waitFor:
      type: file_exists
    outputs:
      mode: notify
---
"""
        )
