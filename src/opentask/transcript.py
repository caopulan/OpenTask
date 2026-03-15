from __future__ import annotations

import json
from typing import Any, Iterable


def extract_last_assistant_final_text(messages: Iterable[dict[str, Any]]) -> str | None:
    fallback_text: str | None = None
    for message in reversed(list(messages)):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue

        final_blocks: list[str] = []
        visible_blocks: list[str] = []
        for block in _content_blocks(message):
            text = _clean_text(block.get("text"))
            if text is None:
                continue
            if _is_final_answer(block):
                final_blocks.append(text)
            else:
                visible_blocks.append(text)

        if final_blocks:
            return "\n\n".join(final_blocks)
        if visible_blocks and str(message.get("stopReason") or "") != "toolUse":
            fallback_text = "\n\n".join(visible_blocks)
            break

        text = _clean_text(message.get("text"))
        if text and str(message.get("stopReason") or "") != "toolUse":
            fallback_text = text
            break
    return fallback_text


def _content_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content")
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict) and block.get("type") == "text"]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.replace("[[reply_to_current]]", "").strip()
    return text or None


def _is_final_answer(block: dict[str, Any]) -> bool:
    signature = block.get("textSignature")
    if not isinstance(signature, str) or not signature.strip():
        return False
    try:
        payload = json.loads(signature)
    except json.JSONDecodeError:
        return False
    return payload.get("phase") == "final_answer"
