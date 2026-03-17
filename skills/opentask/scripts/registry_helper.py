#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NODE_KINDS = {"session_turn", "subagent", "wait", "approval", "summary"}
NODE_STATUSES = {"pending", "ready", "running", "waiting", "completed", "failed", "skipped"}
TERMINAL_NODE_STATUSES = {"completed", "failed", "skipped"}
SATISFIED_DEPENDENCY_STATUSES = {"completed", "skipped"}
RUN_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
STATUS_TO_EVENT = {
    "ready": "node.ready",
    "running": "node.started",
    "waiting": "node.waiting",
    "completed": "node.completed",
    "failed": "node.failed",
    "skipped": "node.skipped",
}
ALLOWED_TRANSITIONS = {
    "pending": {"ready", "failed", "skipped"},
    "ready": {"running", "waiting", "failed", "skipped"},
    "running": {"waiting", "completed", "failed", "skipped"},
    "waiting": {"ready", "running", "failed", "skipped"},
    "failed": {"ready"},
    "skipped": {"ready"},
    "completed": set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fail(message: str) -> None:
    raise SystemExit(message)


def dump_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True))
        handle.write("\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        rows.append(json.loads(raw_line))
    return rows


def parse_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    return json.loads(raw)


def normalize_source_agent_id(source_session_key: str | None, source_agent_id: str | None) -> str | None:
    if source_agent_id:
        return source_agent_id
    if not source_session_key or not source_session_key.startswith("agent:"):
        return None
    parts = source_session_key.split(":")
    if len(parts) > 1:
        return parts[1]
    return None


def normalize_relative_path(path: str) -> str:
    candidate = path.strip().replace("\\", "/")
    if not candidate:
        fail("path must not be empty")
    candidate = candidate.removeprefix("./")
    if candidate.startswith("/"):
        fail(f"path must be relative: {path}")
    if ".." in Path(candidate).parts:
        fail(f"path must not escape the run directory: {path}")
    return candidate


def strip_wrapping_quotes(value: str) -> str:
    candidate = value.strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {'"', "'"}:
        return candidate[1:-1]
    return candidate


def parse_inline_list(raw: str) -> list[str]:
    candidate = raw.strip()
    if candidate == "[]":
        return []
    if not (candidate.startswith("[") and candidate.endswith("]")):
        fail(f"unsupported list syntax: {raw}")
    inner = candidate[1:-1].strip()
    if not inner:
        return []
    return [strip_wrapping_quotes(item.strip()) for item in inner.split(",") if item.strip()]


def extract_frontmatter_text(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        fail(f"workflow is missing YAML frontmatter: {path}")
    closing = content.find("\n---\n", 4)
    if closing == -1:
        fail(f"workflow frontmatter is not properly closed: {path}")
    return content[4:closing]


def parse_workflow_frontmatter(path: Path) -> dict[str, Any]:
    frontmatter = extract_frontmatter_text(path)
    workflow_id: str | None = None
    title: str | None = None
    defaults: dict[str, Any] = {}
    driver: dict[str, Any] = {}
    nodes: list[dict[str, Any]] = []
    current_section: str | None = None
    current_node: dict[str, Any] | None = None
    node_subsection: str | None = None
    skip_block_indent: int | None = None

    def ensure_node() -> dict[str, Any]:
        if current_node is None:
            fail("node property encountered before any node item")
        return current_node

    for raw_line in frontmatter.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()

        if skip_block_indent is not None:
            if indent > skip_block_indent:
                continue
            skip_block_indent = None

        if indent == 0:
            current_section = None
            node_subsection = None
            current_node = None
            if ":" not in stripped:
                fail(f"unsupported frontmatter line: {raw_line}")
            key, value = stripped.split(":", 1)
            value = value.strip()
            if key == "workflowId":
                workflow_id = strip_wrapping_quotes(value)
            elif key == "title":
                title = strip_wrapping_quotes(value)
            elif key == "defaults":
                current_section = "defaults"
            elif key == "driver":
                current_section = "driver"
            elif key == "nodes":
                current_section = "nodes"
            else:
                # Ignore unknown top-level keys in frontmatter.
                current_section = None
            continue

        if current_section in {"defaults", "driver"}:
            if indent < 2 or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            target = defaults if current_section == "defaults" else driver
            parsed_value = value.strip()
            if parsed_value.startswith("[") and parsed_value.endswith("]"):
                target[key] = parse_inline_list(parsed_value)
            elif parsed_value:
                target[key] = strip_wrapping_quotes(parsed_value)
            else:
                target[key] = None
            continue

        if current_section != "nodes":
            continue

        if indent == 2 and stripped.startswith("- "):
            current_node = {
                "needs": [],
                "outputs": {},
                "artifactPaths": [],
            }
            nodes.append(current_node)
            node_subsection = None
            remainder = stripped[2:]
            if remainder:
                if ":" not in remainder:
                    fail(f"unsupported node entry: {raw_line}")
                key, value = remainder.split(":", 1)
                value = value.strip()
                if key == "needs":
                    current_node["needs"] = parse_inline_list(value)
                elif key in {"artifactPaths"} and value:
                    current_node["artifactPaths"] = parse_inline_list(value)
                else:
                    current_node[key] = strip_wrapping_quotes(value)
            continue

        node = ensure_node()

        if indent == 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip()
            if key == "outputs":
                node_subsection = "outputs"
                continue
            if key == "prompt" and value == "|":
                skip_block_indent = 4
                node_subsection = None
                continue
            if key in {"needs", "artifactPaths"}:
                if value:
                    node[key] = parse_inline_list(value)
                    node_subsection = None
                else:
                    node[key] = []
                    node_subsection = key
            elif key == "waitFor":
                node["waitFor"] = strip_wrapping_quotes(value)
                node_subsection = None
            elif key in {"id", "title", "kind", "prompt"}:
                node[key] = strip_wrapping_quotes(value)
                node_subsection = None
            else:
                node[key] = strip_wrapping_quotes(value) if value else None
                node_subsection = None
            continue

        if indent == 6 and node_subsection == "outputs" and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip()
            if key in {"requiredFiles", "artifactPaths"} and value:
                node["outputs"][key] = parse_inline_list(value)
                node_subsection = key
            else:
                node["outputs"][key] = strip_wrapping_quotes(value) if value else None
                node_subsection = key if key in {"requiredFiles", "artifactPaths"} and not value else None
            continue

        if indent == 6 and stripped.startswith("- ") and node_subsection in {"needs", "artifactPaths"}:
            node[node_subsection].append(strip_wrapping_quotes(stripped[2:]))
            continue

        if indent == 8 and stripped.startswith("- ") and node_subsection in {"requiredFiles", "artifactPaths"}:
            node["outputs"].setdefault(node_subsection, []).append(normalize_relative_path(strip_wrapping_quotes(stripped[2:])))
            continue

    return {
        "workflowId": workflow_id,
        "title": title,
        "defaults": defaults,
        "driver": driver,
        "nodes": nodes,
    }


def resolve_registry_root(raw: str | None) -> Path:
    configured = raw or os.getenv("OPENTASK_REGISTRY_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.cwd().resolve()


def resolve_workflow_path(registry_root: Path, raw_path: str) -> tuple[Path, str]:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        relative = resolved.relative_to(registry_root)
        return resolved, str(relative)
    relative = normalize_relative_path(raw_path)
    return (registry_root / relative).resolve(), relative


def working_memory_paths(node_id: str, kind: str) -> dict[str, str] | None:
    if kind not in {"session_turn", "subagent", "summary"}:
        return None
    payload: dict[str, str] = {
        "plan": f"nodes/{node_id}/plan.md",
        "findings": f"nodes/{node_id}/findings.md",
        "progress": f"nodes/{node_id}/progress.md",
    }
    if kind == "subagent":
        payload["handoff"] = f"nodes/{node_id}/handoff.md"
    return payload


def default_plan(node: dict[str, Any]) -> str:
    return (
        f"# {node['title']} plan\n\n"
        f"- Node ID: `{node['id']}`\n"
        f"- Kind: `{node['kind']}`\n"
        f"- Status: `{node['status']}`\n\n"
        "Use this file only if this node expands into multiple concrete steps.\n"
        "Keep the plan scoped to this node; do not duplicate the global workflow here.\n"
    )


def default_findings(node: dict[str, Any]) -> str:
    return (
        f"# {node['title']} findings\n\n"
        "Record node-local discoveries, source links, and intermediate conclusions here.\n"
    )


def default_progress(node: dict[str, Any]) -> str:
    return (
        f"# {node['title']} progress\n\n"
        "Append concise node-local execution updates here when the node spans multiple steps.\n"
    )


def default_handoff(node: dict[str, Any]) -> str:
    return (
        f"# {node['title']} handoff\n\n"
        "The parent orchestrator can place the concrete child brief for this node here before dispatch.\n"
    )


def ensure_file_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")


def require_run_dir(registry_root: Path, run_id: str) -> Path:
    run_dir = registry_root / "runs" / run_id
    if not run_dir.exists():
        fail(f"run not found: {run_id}")
    return run_dir


def require_node(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in state["nodes"]:
        if node["id"] == node_id:
            return node
    fail(f"node not found: {node_id}")


def node_status_counts(nodes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in NODE_STATUSES}
    for node in nodes:
        counts[node["status"]] += 1
    return counts


def compute_run_status(current_status: str, nodes: list[dict[str, Any]]) -> str:
    if current_status in {"paused", "cancelled"}:
        if all(node["status"] in TERMINAL_NODE_STATUSES for node in nodes):
            return "failed" if any(node["status"] == "failed" for node in nodes) else "completed"
        return current_status
    if all(node["status"] in TERMINAL_NODE_STATUSES for node in nodes):
        return "failed" if any(node["status"] == "failed" for node in nodes) else "completed"
    return "running"


def load_run_files(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    state = load_json(run_dir / "state.json")
    refs = load_json(run_dir / "refs.json")
    events = load_jsonl(run_dir / "events.jsonl")
    return state, refs, events


def append_event(events_path: Path, *, run_id: str, event: str, node_id: str | None = None, message: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    item = {
        "event": event,
        "timestamp": utc_now(),
        "runId": run_id,
        "payload": payload or {},
    }
    if node_id:
        item["nodeId"] = node_id
    if message:
        item["message"] = message
    append_jsonl(events_path, item)
    return item


def parse_workflow_spec(path: Path) -> dict[str, Any]:
    return normalize_workflow_spec(load_json(path))


def normalize_workflow_spec(spec: dict[str, Any]) -> dict[str, Any]:
    workflow_id = spec.get("workflowId")
    title = spec.get("title")
    nodes = spec.get("nodes")
    if not workflow_id or not isinstance(workflow_id, str):
        fail("spec.workflowId is required")
    if not title or not isinstance(title, str):
        fail("spec.title is required")
    if not isinstance(nodes, list) or not nodes:
        fail("spec.nodes must be a non-empty list")

    seen_ids: set[str] = set()
    normalized_nodes: list[dict[str, Any]] = []
    for raw_node in nodes:
        node_id = raw_node.get("id")
        title_value = raw_node.get("title")
        kind = raw_node.get("kind")
        if not node_id or not isinstance(node_id, str):
            fail("every spec node requires an id")
        if node_id in seen_ids:
            fail(f"duplicate node id in spec: {node_id}")
        seen_ids.add(node_id)
        if not title_value or not isinstance(title_value, str):
            fail(f"node {node_id} requires title")
        if kind not in NODE_KINDS:
            fail(f"node {node_id} has unsupported kind: {kind}")
        needs = raw_node.get("needs") or []
        if not isinstance(needs, list):
            fail(f"node {node_id} needs must be a list")
        outputs = raw_node.get("outputs") or {}
        outputs_mode = outputs.get("mode")
        if outputs_mode not in {"notify", "report"}:
            fail(f"node {node_id} requires outputs.mode notify|report")
        required_files = raw_node.get("artifactPaths") or outputs.get("requiredFiles") or []
        if not isinstance(required_files, list):
            fail(f"node {node_id} artifact paths must be a list")
        artifact_paths = [normalize_relative_path(item) for item in required_files]
        if outputs_mode == "report" and not artifact_paths:
            artifact_paths = [f"nodes/{node_id}/report.md"]
        node_spec: dict[str, Any] = {
            "id": node_id,
            "title": title_value,
            "kind": kind,
            "needs": needs,
            "outputsMode": outputs_mode,
            "artifactPaths": artifact_paths,
            "waitFor": raw_node.get("waitFor"),
        }
        normalized_nodes.append(node_spec)

    known_ids = {node["id"] for node in normalized_nodes}
    for node in normalized_nodes:
        missing = [dependency for dependency in node["needs"] if dependency not in known_ids]
        if missing:
            fail(f"node {node['id']} depends on missing nodes: {', '.join(missing)}")
        node["workingMemory"] = working_memory_paths(node["id"], node["kind"])
        node["status"] = "ready" if not node["needs"] else "pending"
        node["sessionKey"] = None
        node["childSessionKey"] = None
        node["runId"] = None
        node["notes"] = []
        node["startedAt"] = None
        node["completedAt"] = None

    return {
        "workflowId": workflow_id,
        "title": title,
        "defaults": spec.get("defaults") or {},
        "driver": spec.get("driver") or {},
        "nodes": normalized_nodes,
    }


def command_scaffold(args: argparse.Namespace) -> None:
    registry_root = resolve_registry_root(args.registry_root)
    registry_root.mkdir(parents=True, exist_ok=True)
    workflow_path, workflow_relative_path = resolve_workflow_path(registry_root, args.workflow_path)
    if not workflow_path.exists():
        fail(f"workflow not found: {workflow_path}")
    spec = parse_workflow_spec(Path(args.spec_file)) if args.spec_file else normalize_workflow_spec(parse_workflow_frontmatter(workflow_path))
    run_id = args.run_id
    run_dir = registry_root / "runs" / run_id
    if run_dir.exists():
        fail(f"run already exists: {run_id}")
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "nodes").mkdir(parents=True, exist_ok=True)

    source_session_key = args.source_session_key
    source_agent_id = normalize_source_agent_id(source_session_key, args.source_agent_id)
    root_session_key = args.root_session_key or source_session_key
    planner_session_key = args.planner_session_key or root_session_key
    driver_session_key = args.driver_session_key or root_session_key
    delivery_context = parse_json(args.delivery_context_json)

    nodes: list[dict[str, Any]] = []
    for node in spec["nodes"]:
        node_copy = json.loads(json.dumps(node))
        node_dir = run_dir / "nodes" / node_copy["id"]
        node_dir.mkdir(parents=True, exist_ok=True)
        if node_copy["workingMemory"] is not None:
            ensure_file_if_missing(run_dir / node_copy["workingMemory"]["plan"], default_plan(node_copy))
            ensure_file_if_missing(run_dir / node_copy["workingMemory"]["findings"], default_findings(node_copy))
            ensure_file_if_missing(run_dir / node_copy["workingMemory"]["progress"], default_progress(node_copy))
            if node_copy["workingMemory"].get("handoff"):
                ensure_file_if_missing(run_dir / node_copy["workingMemory"]["handoff"], default_handoff(node_copy))
        nodes.append(node_copy)

    created_at = utc_now()
    state = {
        "runId": run_id,
        "workflowId": spec["workflowId"],
        "title": spec["title"],
        "status": "running",
        "sourceSessionKey": source_session_key,
        "sourceAgentId": source_agent_id,
        "deliveryContext": delivery_context,
        "rootSessionKey": root_session_key,
        "plannerSessionKey": planner_session_key,
        "driverSessionKey": driver_session_key,
        "cronJobId": None,
        "updatedAt": created_at,
        "createdAt": created_at,
        "nodes": nodes,
        "lastEvent": "run.created",
        "lastProgressMessage": None,
        "lastProgressMessageAt": None,
    }
    refs = {
        "runId": run_id,
        "sourceSessionKey": source_session_key,
        "sourceAgentId": source_agent_id,
        "deliveryContext": delivery_context,
        "rootSessionKey": root_session_key,
        "plannerSessionKey": planner_session_key,
        "driverSessionKey": driver_session_key,
        "cronJobId": None,
        "driverRunId": None,
        "driverRequestedEventCount": 0,
        "driverRequestedActivityCount": 0,
        "nodeSessions": {},
        "childSessions": {},
        "nodeRunIds": {},
        "appliedControlIds": [],
        "lastProgressEventCount": 0,
    }

    (run_dir / "workflow.lock.md").write_text(workflow_path.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(run_dir / "state.json", state)
    write_json(run_dir / "refs.json", refs)
    (run_dir / "control.jsonl").touch()

    created_event = append_event(
        run_dir / "events.jsonl",
        run_id=run_id,
        event="run.created",
        message=f"Created run scaffold from {workflow_relative_path}.",
        payload={"workflowPath": workflow_relative_path},
    )
    last_event = created_event["event"]
    ready_nodes: list[str] = []
    for node in nodes:
        if node["status"] != "ready":
            continue
        ready_event = append_event(
            run_dir / "events.jsonl",
            run_id=run_id,
            event="node.ready",
            node_id=node["id"],
            message=f"Node {node['id']} is ready for dispatch.",
        )
        ready_nodes.append(node["id"])
        last_event = ready_event["event"]

    state["lastEvent"] = last_event
    state["updatedAt"] = utc_now()
    write_json(run_dir / "state.json", state)
    dump_json(
        {
            "ok": True,
            "runId": run_id,
            "registryRoot": str(registry_root),
            "workflowPath": workflow_relative_path,
            "runPath": str(run_dir.relative_to(registry_root)),
            "readyNodes": ready_nodes,
        }
    )


def command_bind(args: argparse.Namespace) -> None:
    registry_root = resolve_registry_root(args.registry_root)
    run_dir = require_run_dir(registry_root, args.run_id)
    state, refs, _ = load_run_files(run_dir)
    payload = parse_json(args.payload_json) or {}
    node_id = args.node_id
    value = args.value
    if args.kind in {"node-session", "child-session", "node-run"} and not node_id:
        fail(f"--node-id is required for bind kind {args.kind}")
    if args.kind in {"node-session", "child-session", "node-run", "cron"} and not value:
        fail(f"--value is required for bind kind {args.kind}")

    message = args.message
    event_name: str | None = None
    event_node_id: str | None = node_id
    if args.kind == "cron":
        state["cronJobId"] = value
        refs["cronJobId"] = value
        event_name = "run.cron_bound"
        message = message or f"Bound cron {value}."
    elif args.kind == "node-session":
        node = require_node(state, node_id)
        node["sessionKey"] = value
        refs.setdefault("nodeSessions", {})[node_id] = value
        event_name = "node.session_bound"
        message = message or f"Bound node session {value}."
    elif args.kind == "child-session":
        node = require_node(state, node_id)
        node["childSessionKey"] = value
        refs.setdefault("childSessions", {})[node_id] = value
        event_name = "node.child_session_bound"
        message = message or f"Bound child session {value}."
    elif args.kind == "node-run":
        node = require_node(state, node_id)
        node["runId"] = value
        refs.setdefault("nodeRunIds", {})[node_id] = value
        event_name = "node.run_bound"
        message = message or f"Bound node run id {value}."
    elif args.kind == "driver-run":
        refs["driverRunId"] = value
        event_name = "run.driver_bound"
        event_node_id = None
        message = message or f"Bound driver run id {value}."
    else:
        fail(f"unsupported bind kind: {args.kind}")

    state["updatedAt"] = utc_now()
    state["lastEvent"] = event_name
    write_json(run_dir / "state.json", state)
    write_json(run_dir / "refs.json", refs)
    event = append_event(
        run_dir / "events.jsonl",
        run_id=args.run_id,
        event=event_name,
        node_id=event_node_id,
        message=message,
        payload=payload,
    )
    state["updatedAt"] = event["timestamp"]
    state["lastEvent"] = event["event"]
    write_json(run_dir / "state.json", state)
    dump_json({"ok": True, "event": event, "refs": refs})


def maybe_promote_dependents(state: dict[str, Any], run_dir: Path, completed_node_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    nodes_by_id = {node["id"]: node for node in state["nodes"]}
    for node in state["nodes"]:
        if node["status"] != "pending":
            continue
        if completed_node_id not in node["needs"]:
            continue
        if all(nodes_by_id[dependency]["status"] in SATISFIED_DEPENDENCY_STATUSES for dependency in node["needs"]):
            node["status"] = "ready"
            node["completedAt"] = None
            event = append_event(
                run_dir / "events.jsonl",
                run_id=state["runId"],
                event="node.ready",
                node_id=node["id"],
                message=f"Node {node['id']} is ready for dispatch.",
            )
            events.append(event)
    return events


def command_transition_node(args: argparse.Namespace) -> None:
    registry_root = resolve_registry_root(args.registry_root)
    run_dir = require_run_dir(registry_root, args.run_id)
    state, refs, _ = load_run_files(run_dir)
    node = require_node(state, args.node_id)
    current_status = node["status"]
    target_status = args.status
    if target_status not in STATUS_TO_EVENT:
        fail(f"unsupported transition target: {target_status}")
    if current_status == target_status:
        dump_json({"ok": True, "noop": True, "nodeId": args.node_id, "status": current_status})
        return
    if target_status not in ALLOWED_TRANSITIONS[current_status]:
        fail(f"illegal transition for node {args.node_id}: {current_status} -> {target_status}")

    primary_payload = parse_json(args.payload_json) or {}
    primary_message = args.message
    node["status"] = target_status
    transition_time = utc_now()
    if target_status == "ready":
        node["startedAt"] = None
        node["completedAt"] = None
    elif target_status == "running":
        node["startedAt"] = transition_time
        node["completedAt"] = None
    elif target_status == "waiting":
        if not node.get("startedAt"):
            node["startedAt"] = transition_time
        node["completedAt"] = None
    elif target_status in TERMINAL_NODE_STATUSES:
        if not node.get("startedAt") and target_status == "completed":
            node["startedAt"] = transition_time
        node["completedAt"] = transition_time

    primary_event = append_event(
        run_dir / "events.jsonl",
        run_id=args.run_id,
        event=STATUS_TO_EVENT[target_status],
        node_id=args.node_id,
        message=primary_message,
        payload=primary_payload,
    )
    appended_events = [primary_event]
    if target_status in SATISFIED_DEPENDENCY_STATUSES:
        appended_events.extend(maybe_promote_dependents(state, run_dir, args.node_id))

    previous_run_status = state["status"]
    state["status"] = compute_run_status(previous_run_status, state["nodes"])
    if state["status"] != previous_run_status and state["status"] in RUN_TERMINAL_STATUSES:
        terminal_event = append_event(
            run_dir / "events.jsonl",
            run_id=args.run_id,
            event=f"run.{state['status']}",
            message=f"Run {args.run_id} is {state['status']}.",
        )
        appended_events.append(terminal_event)

    state["updatedAt"] = appended_events[-1]["timestamp"]
    state["lastEvent"] = appended_events[-1]["event"]
    write_json(run_dir / "state.json", state)
    write_json(run_dir / "refs.json", refs)
    dump_json({"ok": True, "events": appended_events, "statusCounts": node_status_counts(state["nodes"]), "runStatus": state["status"]})


def command_progress(args: argparse.Namespace) -> None:
    registry_root = resolve_registry_root(args.registry_root)
    run_dir = require_run_dir(registry_root, args.run_id)
    state, refs, _ = load_run_files(run_dir)
    payload = parse_json(args.payload_json) or {}
    event = append_event(
        run_dir / "events.jsonl",
        run_id=args.run_id,
        event="run.progress",
        message=args.message,
        payload=payload,
    )
    state["lastProgressMessage"] = args.message
    state["lastProgressMessageAt"] = event["timestamp"]
    state["updatedAt"] = event["timestamp"]
    state["lastEvent"] = event["event"]
    write_json(run_dir / "state.json", state)
    write_json(run_dir / "refs.json", refs)
    dump_json({"ok": True, "event": event})


def command_validate(args: argparse.Namespace) -> None:
    registry_root = resolve_registry_root(args.registry_root)
    run_dir = require_run_dir(registry_root, args.run_id)
    issues: list[str] = []
    required_paths = [
        run_dir / "workflow.lock.md",
        run_dir / "state.json",
        run_dir / "refs.json",
        run_dir / "events.jsonl",
        run_dir / "control.jsonl",
    ]
    for path in required_paths:
        if not path.exists():
            issues.append(f"missing required file: {path.name}")
    if issues:
        dump_json({"ok": False, "issues": issues})
        raise SystemExit(1)

    state, refs, events = load_run_files(run_dir)
    nodes_by_id = {node["id"]: node for node in state["nodes"]}

    try:
        load_jsonl(run_dir / "control.jsonl")
    except json.JSONDecodeError as exc:
        issues.append(f"control.jsonl contains invalid JSONL: {exc}")

    last_timestamp: datetime | None = None
    per_node_events: dict[str, list[str]] = {node_id: [] for node_id in nodes_by_id}
    for event in events:
        raw_timestamp = event.get("timestamp")
        try:
            current_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
        except Exception:
            issues.append(f"invalid event timestamp: {raw_timestamp}")
            current_timestamp = None
        if current_timestamp and last_timestamp and current_timestamp < last_timestamp:
            issues.append("events.jsonl timestamps are not monotonic")
        if current_timestamp:
            last_timestamp = current_timestamp
        node_id = event.get("nodeId")
        if node_id and node_id in per_node_events:
            per_node_events[node_id].append(event["event"])

    for node in state["nodes"]:
        wm = node.get("workingMemory") or {}
        for key in ("plan", "findings", "progress", "handoff"):
            relative = wm.get(key)
            if relative and not (run_dir / normalize_relative_path(relative)).exists():
                issues.append(f"missing working memory file for {node['id']}: {relative}")
        lifecycle = per_node_events.get(node["id"], [])
        if node["status"] == "ready" and "node.ready" not in lifecycle:
            issues.append(f"node {node['id']} is ready in state but missing node.ready")
        if node["status"] in {"running", "waiting", "completed", "failed", "skipped"} and "node.started" not in lifecycle:
            issues.append(f"node {node['id']} is {node['status']} in state but missing node.started")
        if node["status"] == "completed" and "node.completed" not in lifecycle:
            issues.append(f"node {node['id']} is completed in state but missing node.completed")
        if node["status"] == "failed" and "node.failed" not in lifecycle:
            issues.append(f"node {node['id']} is failed in state but missing node.failed")
        if node["status"] == "waiting" and "node.waiting" not in lifecycle:
            issues.append(f"node {node['id']} is waiting in state but missing node.waiting")
        if node["status"] == "skipped" and "node.skipped" not in lifecycle:
            issues.append(f"node {node['id']} is skipped in state but missing node.skipped")
        if "node.started" in lifecycle and "node.ready" not in lifecycle:
            issues.append(f"node {node['id']} has node.started without node.ready")
        if "node.completed" in lifecycle and "node.started" not in lifecycle:
            issues.append(f"node {node['id']} has node.completed without node.started")

    if all(node["status"] in TERMINAL_NODE_STATUSES for node in state["nodes"]):
        if state["status"] not in RUN_TERMINAL_STATUSES:
            issues.append("run has all terminal nodes but state.status is not terminal")
    if state["status"] == "completed" and any(node["status"] not in TERMINAL_NODE_STATUSES for node in state["nodes"]):
        issues.append("run.state is completed but some nodes are not terminal")

    for node_id, session_key in refs.get("nodeSessions", {}).items():
        node = nodes_by_id.get(node_id)
        if not node:
            issues.append(f"refs.nodeSessions points to missing node {node_id}")
            continue
        if node.get("sessionKey") != session_key:
            issues.append(f"state/refs mismatch for node session {node_id}")
    for node_id, session_key in refs.get("childSessions", {}).items():
        node = nodes_by_id.get(node_id)
        if not node:
            issues.append(f"refs.childSessions points to missing node {node_id}")
            continue
        if node.get("childSessionKey") != session_key:
            issues.append(f"state/refs mismatch for child session {node_id}")
    for node_id, node_run_id in refs.get("nodeRunIds", {}).items():
        node = nodes_by_id.get(node_id)
        if not node:
            issues.append(f"refs.nodeRunIds points to missing node {node_id}")
            continue
        if node.get("runId") != node_run_id:
            issues.append(f"state/refs mismatch for node run id {node_id}")

    payload = {
        "ok": not issues,
        "issues": issues,
        "runId": state["runId"],
        "runStatus": state["status"],
        "statusCounts": node_status_counts(state["nodes"]),
        "eventCount": len(events),
    }
    dump_json(payload)
    if issues:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="registry_helper")
    parser.add_argument("--registry-root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold = subparsers.add_parser("scaffold")
    scaffold.add_argument("--workflow-path", required=True)
    scaffold.add_argument("--spec-file")
    scaffold.add_argument("--run-id", required=True)
    scaffold.add_argument("--source-session-key", required=True)
    scaffold.add_argument("--source-agent-id")
    scaffold.add_argument("--delivery-context-json")
    scaffold.add_argument("--root-session-key")
    scaffold.add_argument("--planner-session-key")
    scaffold.add_argument("--driver-session-key")
    scaffold.set_defaults(handler=command_scaffold)

    bind = subparsers.add_parser("bind")
    bind.add_argument("run_id")
    bind.add_argument("kind", choices=["cron", "node-session", "child-session", "node-run", "driver-run"])
    bind.add_argument("--node-id")
    bind.add_argument("--value")
    bind.add_argument("--message")
    bind.add_argument("--payload-json")
    bind.set_defaults(handler=command_bind)

    transition = subparsers.add_parser("transition-node")
    transition.add_argument("run_id")
    transition.add_argument("node_id")
    transition.add_argument("status", choices=["ready", "running", "waiting", "completed", "failed", "skipped"])
    transition.add_argument("--message")
    transition.add_argument("--payload-json")
    transition.set_defaults(handler=command_transition_node)

    progress = subparsers.add_parser("progress")
    progress.add_argument("run_id")
    progress.add_argument("message")
    progress.add_argument("--payload-json")
    progress.set_defaults(handler=command_progress)

    validate = subparsers.add_parser("validate")
    validate.add_argument("run_id")
    validate.set_defaults(handler=command_validate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
