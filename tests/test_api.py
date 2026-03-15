from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from opentask.api.main import create_app
from opentask.openclaw_client import OpenClawGatewayError
from opentask.service import OpenTaskService
from opentask.store import RunStore
from tests.test_service import FakeGateway


@pytest.mark.asyncio
async def test_api_create_and_fetch_run(tmp_path: Path) -> None:
    app = create_app(
        OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=FakeGateway())
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post(
            "/api/runs",
            json={"taskText": "Inspect this task", "title": "API demo"},
        )
        assert create_res.status_code == 200
        created = create_res.json()

        get_res = await client.get(f"/api/runs/{created['runId']}")
        assert get_res.status_code == 200
        assert get_res.json()["runId"] == created["runId"]

        list_res = await client.get("/api/runs")
        assert list_res.status_code == 200
        assert len(list_res.json()) == 1


@pytest.mark.asyncio
async def test_api_approve_action(tmp_path: Path) -> None:
    markdown = """---
workflowId: api-approval
title: API approval
nodes:
  - id: first
    title: First
    kind: session_turn
    needs: []
    prompt: First
    outputs:
      mode: report
  - id: gate
    title: Gate
    kind: approval
    needs: [first]
    prompt: Wait
    outputs:
      mode: notify
  - id: summary
    title: Summary
    kind: summary
    needs: [gate]
    prompt: Done
    outputs:
      mode: report
---
"""
    app = create_app(
        OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=FakeGateway())
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post("/api/runs", json={"workflowMarkdown": markdown})
        run_id = create_res.json()["runId"]

        tick_res = await client.post(f"/api/runs/{run_id}/actions/tick", json={})
        gate = next(node for node in tick_res.json()["nodes"] if node["id"] == "gate")
        assert gate["status"] == "waiting"

        approve_res = await client.post(
            f"/api/runs/{run_id}/actions/approve",
            json={"nodeId": "gate"},
        )
        assert approve_res.status_code == 200
        approved_gate = next(node for node in approve_res.json()["nodes"] if node["id"] == "gate")
        assert approved_gate["status"] == "completed"


class FailingGateway(FakeGateway):
    async def send_chat(self, **kwargs):
        raise OpenClawGatewayError("INVALID_REQUEST", "invalid chat.send params")


@pytest.mark.asyncio
async def test_api_returns_gateway_errors_as_502(tmp_path: Path) -> None:
    app = create_app(
        OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=FailingGateway())
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/runs",
            json={"taskText": "Inspect this task", "title": "API failure demo"},
        )

    assert response.status_code == 502
    assert "gateway error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_list_runs_tolerates_forward_compatible_runtime_fields(tmp_path: Path) -> None:
    runtime_root = tmp_path / ".opentask"
    app = create_app(OpenTaskService(store=RunStore(runtime_root=runtime_root), gateway=FakeGateway()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post(
            "/api/runs",
            json={"taskText": "Inspect this task", "title": "Compat demo"},
        )
        run_id = create_res.json()["runId"]

        state_path = runtime_root / "runs" / run_id / "state.json"
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        payload["lastDriverTickAt"] = "2026-03-15T11:46:00Z"
        state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        list_res = await client.get("/api/runs")

    assert list_res.status_code == 200
    assert list_res.json()[0]["runId"] == run_id


@pytest.mark.asyncio
async def test_api_send_message_action(tmp_path: Path) -> None:
    gateway = FakeGateway()
    app = create_app(OpenTaskService(store=RunStore(runtime_root=tmp_path / ".opentask"), gateway=gateway))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_res = await client.post(
            "/api/runs",
            json={
                "taskText": "Send an update",
                "title": "Messaging demo",
                "sourceSessionKey": "agent:main:discord:channel:123",
                "sourceAgentId": "main",
                "deliveryContext": {"channel": "discord", "to": "channel:123"},
            },
        )
        run_id = create_res.json()["runId"]

        message_res = await client.post(
            f"/api/runs/{run_id}/actions/send_message",
            json={"message": "still working"},
        )

    assert message_res.status_code == 200
    assert message_res.json()["lastProgressMessage"] == "still working"
    assert gateway.outbound_messages[-1]["to"] == "channel:123"
