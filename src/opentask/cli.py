from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .models import CreateRunRequest, DeliveryContext, NodeResult, RunActionRequest, RunEvent
from .service import OpenTaskService
from .store import RunStore
from .workflow import load_workflow


def _load_delivery_context(raw: str | None) -> DeliveryContext | None:
    if not raw:
        return None
    return DeliveryContext.model_validate(json.loads(raw))


def _print_json(payload: dict[str, Any] | list[Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


async def _run_create(args: argparse.Namespace) -> None:
    workflow_markdown = None
    if args.workflow_markdown_file:
        workflow_markdown = Path(args.workflow_markdown_file).read_text(encoding="utf-8")
    elif args.workflow_markdown:
        workflow_markdown = args.workflow_markdown

    request = CreateRunRequest(
        workflowPath=args.workflow_path,
        workflowMarkdown=workflow_markdown,
        taskText=args.task_text,
        title=args.title,
        sourceSessionKey=args.source_session_key,
        sourceAgentId=args.source_agent_id,
        deliveryContext=_load_delivery_context(args.delivery_context_json),
        rootSessionKey=args.root_session_key,
    )
    state = await OpenTaskService().create_run(request)
    _print_json(state.model_dump(by_alias=True, exclude_none=True))


async def _run_bind(args: argparse.Namespace) -> None:
    service = OpenTaskService()
    state = await service.bind_run(
        args.run_id,
        source_session_key=args.source_session_key,
        source_agent_id=args.source_agent_id,
        delivery_context=_load_delivery_context(args.delivery_context_json),
        root_session_key=args.root_session_key,
    )
    _print_json(state.model_dump(by_alias=True, exclude_none=True))


async def _workflow_validate(args: argparse.Namespace) -> None:
    workflow = load_workflow(Path(args.path))
    _print_json(workflow.definition.model_dump(by_alias=True, exclude_none=True))


async def _run_action(args: argparse.Namespace) -> None:
    service = OpenTaskService()
    request = RunActionRequest(
        nodeId=args.node_id,
        message=args.message,
        patch=json.loads(args.patch_json) if args.patch_json else {},
    )
    action = args.action
    if action == "pause":
        state = await service.pause_run(args.run_id)
    elif action == "resume":
        state = await service.resume_run(args.run_id)
    elif action == "retry":
        state = await service.retry_node(args.run_id, request.node_id or "")
    elif action == "skip":
        state = await service.skip_node(args.run_id, request.node_id or "")
    elif action == "approve":
        state = await service.approve_node(args.run_id, request.node_id or "")
    elif action == "send_message":
        state = await service.send_message(args.run_id, request.message or "")
    elif action == "patch_cron":
        state = await service.patch_cron(args.run_id, request.patch)
    else:
        raise ValueError(f"unsupported action: {action}")
    _print_json(state.model_dump(by_alias=True, exclude_none=True))


async def _event_append(args: argparse.Namespace) -> None:
    store = RunStore()
    event = RunEvent(
        event=args.event,
        runId=args.run_id,
        nodeId=args.node_id,
        message=args.message,
        payload=json.loads(args.payload_json) if args.payload_json else {},
    )
    store.append_event(args.run_id, event)
    _print_json(event.model_dump(by_alias=True, exclude_none=True))


async def _node_result(args: argparse.Namespace) -> None:
    store = RunStore()
    payload = json.loads(args.payload_json) if args.payload_json else {}
    artifacts = json.loads(args.artifacts_json) if args.artifacts_json else []
    result = NodeResult(
        runId=args.run_id,
        nodeId=args.node_id,
        status=args.status,
        summary=args.summary,
        artifacts=artifacts,
        sessionKey=args.session_key,
        childSessionKey=args.child_session_key,
        payload=payload,
    )
    path = store.write_node_result(args.run_id, args.node_id, result)
    _print_json({"path": path, "result": result.model_dump(by_alias=True, exclude_none=True)})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opentask")
    subparsers = parser.add_subparsers(dest="command", required=True)

    workflow_parser = subparsers.add_parser("workflow")
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command", required=True)
    workflow_validate = workflow_subparsers.add_parser("validate")
    workflow_validate.add_argument("path")
    workflow_validate.set_defaults(handler=_workflow_validate)

    run_parser = subparsers.add_parser("run")
    run_subparsers = run_parser.add_subparsers(dest="run_command", required=True)

    run_create = run_subparsers.add_parser("create")
    run_create.add_argument("--workflow-path")
    run_create.add_argument("--workflow-markdown")
    run_create.add_argument("--workflow-markdown-file")
    run_create.add_argument("--task-text")
    run_create.add_argument("--title")
    run_create.add_argument("--source-session-key")
    run_create.add_argument("--source-agent-id")
    run_create.add_argument("--delivery-context-json")
    run_create.add_argument("--root-session-key")
    run_create.set_defaults(handler=_run_create)

    run_bind = run_subparsers.add_parser("bind")
    run_bind.add_argument("run_id")
    run_bind.add_argument("--source-session-key")
    run_bind.add_argument("--source-agent-id")
    run_bind.add_argument("--delivery-context-json")
    run_bind.add_argument("--root-session-key")
    run_bind.set_defaults(handler=_run_bind)

    control_parser = subparsers.add_parser("control")
    control_parser.add_argument("action", choices=["pause", "resume", "retry", "skip", "approve", "send_message", "patch_cron"])
    control_parser.add_argument("run_id")
    control_parser.add_argument("--node-id")
    control_parser.add_argument("--message")
    control_parser.add_argument("--patch-json")
    control_parser.set_defaults(handler=_run_action)

    event_parser = subparsers.add_parser("event")
    event_subparsers = event_parser.add_subparsers(dest="event_command", required=True)
    event_append = event_subparsers.add_parser("append")
    event_append.add_argument("run_id")
    event_append.add_argument("event")
    event_append.add_argument("--node-id")
    event_append.add_argument("--message")
    event_append.add_argument("--payload-json")
    event_append.set_defaults(handler=_event_append)

    node_parser = subparsers.add_parser("node")
    node_subparsers = node_parser.add_subparsers(dest="node_command", required=True)
    node_result = node_subparsers.add_parser("result")
    node_result.add_argument("run_id")
    node_result.add_argument("node_id")
    node_result.add_argument("status")
    node_result.add_argument("--summary")
    node_result.add_argument("--artifacts-json")
    node_result.add_argument("--payload-json")
    node_result.add_argument("--session-key")
    node_result.add_argument("--child-session-key")
    node_result.set_defaults(handler=_node_result)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(args.handler(args))

