from __future__ import annotations


def qualify_agent_session_key(session_key: str, agent_id: str) -> str:
    if session_key.startswith("agent:"):
        return session_key
    normalized_agent_id = agent_id.strip() or "main"
    return f"agent:{normalized_agent_id}:{session_key}"


def render_agent_session_key(template: str, *, run_id: str, agent_id: str) -> str:
    rendered = template.format(run_id=run_id, agent_id=agent_id)
    return qualify_agent_session_key(rendered, agent_id)
