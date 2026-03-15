from __future__ import annotations

import json
import re
from typing import Any, Iterable

from .models import DriverMutationDirective

MUTATION_BLOCK_RE = re.compile(
    r"<opentask-mutation>\s*(\{.*?\})\s*</opentask-mutation>",
    re.DOTALL,
)


def driver_mutation_instructions() -> str:
    return (
        "If you need to change the workflow graph, emit an "
        "<opentask-mutation>{...}</opentask-mutation> block with JSON only.\n"
        'Use this schema: {"id":"unique-directive-id","summary":"why",'
        '"mutations":[{"kind":"add_node","node":{...}},'
        '{"kind":"rewire_node","nodeId":"summary","needs":["new-node"]}]}\n'
        "Use a fresh id every time. Supported mutation kinds are add_node and rewire_node.\n"
        "Do not repeat directives that were already applied."
    )


def extract_driver_directives(messages: Iterable[dict[str, Any]]) -> list[DriverMutationDirective]:
    directives: list[DriverMutationDirective] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        text = _message_text(message)
        if not text:
            continue
        for match in MUTATION_BLOCK_RE.finditer(text):
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            try:
                directives.append(DriverMutationDirective.model_validate(_normalize_directive_payload(payload)))
            except Exception:
                continue
    return directives


def _normalize_directive_payload(payload: dict[str, Any]) -> dict[str, Any]:
    mutations = payload.get("mutations")
    if not isinstance(mutations, list):
        return payload

    normalized_mutations: list[Any] = []
    for mutation in mutations:
        if not isinstance(mutation, dict) or mutation.get("kind") != "add_node":
            normalized_mutations.append(mutation)
            continue
        normalized_mutations.append(_normalize_add_node_mutation(mutation))
    return {**payload, "mutations": normalized_mutations}


def _normalize_add_node_mutation(mutation: dict[str, Any]) -> dict[str, Any]:
    node = mutation.get("node")
    if not isinstance(node, dict):
        return mutation

    node_id = str(node.get("id") or "").strip()
    kind = str(node.get("kind") or "").strip()
    normalized_node = dict(node)

    if node_id and not str(normalized_node.get("title") or "").strip():
        normalized_node["title"] = _title_from_node_id(node_id)

    if "needs" not in normalized_node:
        normalized_node["needs"] = []

    if kind in {"session_turn", "subagent"} and not str(normalized_node.get("prompt") or "").strip():
        normalized_node["prompt"] = _prompt_from_node_title(str(normalized_node.get("title") or node_id))

    outputs = normalized_node.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
    normalized_outputs = dict(outputs)
    if "mode" not in normalized_outputs:
        normalized_outputs["mode"] = "notify" if kind in {"wait", "approval"} else "report"
    if normalized_outputs.get("mode") == "report":
        required_files = normalized_outputs.get("requiredFiles")
        path = normalized_outputs.get("path")
        if not path and (not isinstance(required_files, list) or not required_files):
            normalized_outputs["requiredFiles"] = [f"nodes/{node_id}/report.md"] if node_id else []
    normalized_node["outputs"] = normalized_outputs

    return {**mutation, "node": normalized_node}


def _title_from_node_id(node_id: str) -> str:
    return node_id.replace("_", " ").replace("-", " ").strip().title() or node_id


def _prompt_from_node_title(title: str) -> str:
    cleaned = " ".join(title.split()).strip()
    if not cleaned:
        cleaned = "Follow-up Task"
    return (
        f"Review the dependency artifacts and complete this follow-up task: {cleaned}. "
        "Produce a concise report with findings and next steps."
    )


def _message_text(message: dict[str, Any]) -> str:
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text

    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text_value = block.get("text")
        if isinstance(text_value, str) and text_value.strip():
            parts.append(text_value)
    return "\n".join(parts)
