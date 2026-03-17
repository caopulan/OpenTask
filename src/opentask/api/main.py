from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from watchfiles import Change, awatch

from opentask.models import CreateRunRequest, RunActionRequest
from opentask.openclaw_client import OpenClawGatewayError
from opentask.service import OpenTaskService


async def _watch_runtime(service: OpenTaskService, stop_event: asyncio.Event) -> None:
    runtime_root = service.store.runs_root
    runtime_root.mkdir(parents=True, exist_ok=True)
    async for changes in awatch(runtime_root, stop_event=stop_event):
        run_ids = set()
        for _, path in changes:
            parts = Path(path).parts
            if "runs" not in parts:
                continue
            runs_index = parts.index("runs")
            if runs_index + 1 < len(parts):
                run_ids.add(parts[runs_index + 1])
        for run_id in sorted(run_ids):
            with suppress(FileNotFoundError):
                await service._publish(service.get_run(run_id))


async def _poll_active_runs(service: OpenTaskService, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        for run in service.list_runs():
            if run.status == "running":
                with suppress(Exception):
                    await service.tick_run(run.run_id)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=5)
        except TimeoutError:
            continue


def _serialize(model) -> dict:
    return model.model_dump(by_alias=True, exclude_none=True)


def create_app(service: OpenTaskService | None = None) -> FastAPI:
    service = service or OpenTaskService()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        stop_event = asyncio.Event()
        watch_task = asyncio.create_task(_watch_runtime(service, stop_event))
        poll_task = asyncio.create_task(_poll_active_runs(service, stop_event))
        _app.state.service = service
        _app.state.stop_event = stop_event
        try:
            yield
        finally:
            stop_event.set()
            for task in (watch_task, poll_task):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="OpenTask", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/runs")
    async def list_runs() -> list[dict]:
        return [_serialize(run) for run in service.list_runs()]

    @app.post("/api/runs")
    async def create_run(request: CreateRunRequest) -> dict:
        try:
            run = await service.create_run(request)
            return _serialize(run)
        except OpenClawGatewayError as exc:
            raise HTTPException(status_code=502, detail=f"gateway error: {exc}") from exc

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict:
        try:
            return _serialize(service.get_run(run_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc

    @app.get("/api/runs/{run_id}/events")
    async def get_events(run_id: str) -> list[dict]:
        try:
            return [_serialize(event) for event in service.get_events(run_id)]
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc

    @app.get("/api/runs/{run_id}/nodes/{node_id}/documents")
    async def get_node_documents(run_id: str, node_id: str) -> list[dict]:
        try:
            return [_serialize(document) for document in service.get_node_documents(run_id, node_id)]
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/actions/{action}")
    async def run_action(run_id: str, action: str, request: RunActionRequest | None = None) -> dict:
        payload = request or RunActionRequest()
        try:
            if action == "pause":
                run = await service.pause_run(run_id)
            elif action == "resume":
                run = await service.resume_run(run_id)
            elif action == "retry":
                if not payload.node_id:
                    raise HTTPException(status_code=400, detail="nodeId is required for retry")
                run = await service.retry_node(run_id, payload.node_id)
            elif action == "skip":
                if not payload.node_id:
                    raise HTTPException(status_code=400, detail="nodeId is required for skip")
                run = await service.skip_node(run_id, payload.node_id)
            elif action == "approve":
                if not payload.node_id:
                    raise HTTPException(status_code=400, detail="nodeId is required for approve")
                run = await service.approve_node(run_id, payload.node_id)
            elif action == "send_message":
                if not payload.message:
                    raise HTTPException(status_code=400, detail="message is required for send_message")
                run = await service.send_message(run_id, payload.message)
            elif action == "patch_cron":
                run = await service.patch_cron(run_id, payload.patch)
            elif action == "tick":
                run = await service.force_tick(run_id)
            else:
                raise HTTPException(status_code=404, detail=f"unknown action: {action}")
            return _serialize(run)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc
        except OpenClawGatewayError as exc:
            raise HTTPException(status_code=502, detail=f"gateway error: {exc}") from exc

    @app.websocket("/api/runs/{run_id}/stream")
    async def run_stream(websocket: WebSocket, run_id: str) -> None:
        queue = service.subscribe(run_id)
        await websocket.accept()
        try:
            await websocket.send_json(_serialize(service.get_run(run_id)))
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except FileNotFoundError:
            await websocket.close(code=4404, reason="run not found")
        except WebSocketDisconnect:
            pass
        finally:
            service.unsubscribe(run_id, queue)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("opentask.api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
