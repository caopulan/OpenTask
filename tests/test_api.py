from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from opentask.api.main import create_app
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
