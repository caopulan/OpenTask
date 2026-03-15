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
                directives.append(DriverMutationDirective.model_validate(payload))
            except Exception:
                continue
    return directives


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
