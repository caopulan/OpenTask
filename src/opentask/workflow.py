from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable

import yaml

from .models import ParsedWorkflow, RunEvent, WorkflowDefinition, WorkflowNode, WorkflowOutputs


class WorkflowValidationError(ValueError):
    """Raised when workflow frontmatter is structurally invalid."""


def _split_frontmatter(markdown: str) -> tuple[dict, str]:
    text = markdown.lstrip()
    if not text.startswith("---"):
        raise WorkflowValidationError("workflow markdown must start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise WorkflowValidationError("workflow markdown frontmatter is incomplete")
    _, frontmatter_text, body = parts
    raw = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(raw, dict):
        raise WorkflowValidationError("workflow frontmatter must decode to an object")
    return raw, body.lstrip("\n")


def _validate_graph(workflow: WorkflowDefinition) -> None:
    nodes_by_id = {}
    duplicates: list[str] = []
    for node in workflow.nodes:
        if node.id in nodes_by_id:
            duplicates.append(node.id)
        nodes_by_id[node.id] = node
    if duplicates:
        dupes = ", ".join(sorted(set(duplicates)))
        raise WorkflowValidationError(f"duplicate node ids: {dupes}")

    missing: list[str] = []
    incoming: dict[str, int] = {node.id: 0 for node in workflow.nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node in workflow.nodes:
        for dependency in node.needs:
            if dependency not in nodes_by_id:
                missing.append(f"{node.id}->{dependency}")
                continue
            incoming[node.id] += 1
            outgoing[dependency].append(node.id)

    if missing:
        refs = ", ".join(missing)
        raise WorkflowValidationError(f"missing node dependencies: {refs}")

    queue = deque(sorted(node_id for node_id, count in incoming.items() if count == 0))
    visited: list[str] = []
    while queue:
        node_id = queue.popleft()
        visited.append(node_id)
        for successor in outgoing[node_id]:
            incoming[successor] -= 1
            if incoming[successor] == 0:
                queue.append(successor)

    if len(visited) != len(workflow.nodes):
        cycle_ids = sorted(node_id for node_id, count in incoming.items() if count > 0)
        raise WorkflowValidationError(f"workflow contains dependency cycles: {', '.join(cycle_ids)}")


def parse_workflow_markdown(markdown: str, *, source_path: str | None = None) -> ParsedWorkflow:
    frontmatter, body = _split_frontmatter(markdown)
    definition = WorkflowDefinition.model_validate(frontmatter)
    _validate_graph(definition)
    return ParsedWorkflow(definition=definition, body=body, sourcePath=source_path)


def validate_workflow_definition(workflow: WorkflowDefinition) -> WorkflowDefinition:
    _validate_graph(workflow)
    return workflow


def load_workflow(path: Path) -> ParsedWorkflow:
    return parse_workflow_markdown(path.read_text(encoding="utf-8"), source_path=str(path))


def render_workflow_markdown(parsed: ParsedWorkflow) -> str:
    payload = parsed.definition.model_dump(by_alias=True, exclude_none=True)
    yaml_blob = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False).strip()
    body = parsed.body.rstrip()
    if body:
        return f"---\n{yaml_blob}\n---\n\n{body}\n"
    return f"---\n{yaml_blob}\n---\n"


def leaf_node_ids(workflow: WorkflowDefinition) -> list[str]:
    referenced = {dependency for node in workflow.nodes for dependency in node.needs}
    return sorted(node.id for node in workflow.nodes if node.id not in referenced)


def ensure_summary_node(parsed: ParsedWorkflow) -> tuple[ParsedWorkflow, list[RunEvent]]:
    if any(node.kind == "summary" for node in parsed.definition.nodes):
        return parsed, []

    leafs = leaf_node_ids(parsed.definition)
    summary_node = WorkflowNode(
        id="summary",
        title="Workflow summary",
        kind="summary",
        needs=leafs,
        prompt="Summarize workflow artifacts and final status.",
        outputs=WorkflowOutputs(mode="report", requiredFiles=["nodes/summary/report.md"]),
    )
    amended = parsed.model_copy(
        update={
            "definition": parsed.definition.model_copy(
                update={"nodes": [*parsed.definition.nodes, summary_node]},
            )
        }
    )
    _validate_graph(amended.definition)
    events = [
        RunEvent(
            event="node.added",
            runId="bootstrap",
            nodeId="summary",
            message="Added implicit summary node because the workflow had no terminal summary node.",
            payload={"needs": leafs},
        )
    ]
    return amended, events


def build_starter_workflow(title: str, task_text: str) -> ParsedWorkflow:
    definition = WorkflowDefinition.model_validate(
        {
            "workflowId": slugify(title),
            "title": title,
            "driver": {
                "cron": "*/2 * * * *",
                "wakeMode": "now",
                "sessionKeyTemplate": "session:workflow:{run_id}:driver",
                "plannerSessionKeyTemplate": "session:workflow:{run_id}:planner",
            },
            "nodes": [
                {
                    "id": "execute-task",
                    "title": "Execute task",
                    "kind": "session_turn",
                    "needs": [],
                    "prompt": task_text,
                    "outputs": {
                        "mode": "report",
                        "requiredFiles": ["nodes/execute-task/report.md"],
                    },
                }
            ],
        }
    )
    parsed = ParsedWorkflow(definition=definition, body=f"# Objective\n\n{task_text}\n")
    return ensure_summary_node(parsed)[0]


def slugify(value: str) -> str:
    allowed = []
    for character in value.lower():
        if character.isalnum():
            allowed.append(character)
        elif character in {" ", "-", "_"}:
            allowed.append("-")
    collapsed = "".join(allowed).strip("-")
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return collapsed or "workflow"


def normalize_artifact_paths(node: WorkflowNode) -> list[str]:
    paths: list[str] = []
    if node.outputs.path:
        paths.append(node.outputs.path)
    paths.extend(node.outputs.required_files)
    return sorted(dict.fromkeys(paths))


def ensure_relative_paths(paths: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for raw in paths:
        if raw.startswith("/"):
            raise WorkflowValidationError(f"artifact path must be relative: {raw}")
        normalized.append(raw)
    return normalized
