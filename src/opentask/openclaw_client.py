from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import connect

from .config import get_settings

PROTOCOL_VERSION = 3


class OpenClawGatewayError(RuntimeError):
    def __init__(self, code: str, message: str, details: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(slots=True)
class OpenClawClient:
    url: str | None = None
    token: str | None = None
    password: str | None = None
    role: str = "operator"
    scopes: list[str] | None = None
    version: str = "0.1.0"

    def __post_init__(self) -> None:
        settings = get_settings()
        if self.url is None:
            self.url = settings.gateway_url
        if self.token is None:
            self.token = settings.gateway_token
        if self.password is None:
            self.password = settings.gateway_password
        if self.scopes is None:
            self.scopes = settings.gateway_scopes

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        expect_final: bool = False,
        timeout_ms: int = 30_000,
    ) -> Any:
        connect_timeout = max(timeout_ms / 1000, 5)
        async with connect(str(self.url), open_timeout=connect_timeout, max_size=25 * 1024 * 1024) as ws:
            nonce: str | None = None
            connect_id = uuid4().hex
            request_id = uuid4().hex
            connected = False

            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=connect_timeout)
                frame = json.loads(raw)
                frame_type = frame.get("type")
                if frame_type == "event" and frame.get("event") == "connect.challenge":
                    payload = frame.get("payload") or {}
                    nonce = payload.get("nonce")
                    await ws.send(
                        json.dumps(
                            {
                                "type": "req",
                                "id": connect_id,
                                "method": "connect",
                                "params": self._connect_params(nonce),
                            }
                        )
                    )
                    continue

                if frame_type != "res":
                    continue

                if frame.get("id") == connect_id:
                    if not frame.get("ok"):
                        error = frame.get("error") or {}
                        raise OpenClawGatewayError(
                            error.get("code", "connect_failed"),
                            error.get("message", "gateway connect failed"),
                            error.get("details"),
                        )
                    connected = True
                    await ws.send(
                        json.dumps(
                            {
                                "type": "req",
                                "id": request_id,
                                "method": method,
                                "params": params or {},
                            }
                        )
                    )
                    continue

                if not connected or frame.get("id") != request_id:
                    continue

                payload = frame.get("payload")
                if expect_final and isinstance(payload, dict) and payload.get("status") == "accepted":
                    continue
                if not frame.get("ok"):
                    error = frame.get("error") or {}
                    raise OpenClawGatewayError(
                        error.get("code", "request_failed"),
                        error.get("message", f"gateway request failed: {method}"),
                        error.get("details"),
                    )
                return payload

    async def send_chat(
        self,
        *,
        session_key: str,
        message: str,
        idempotency_key: str,
        timeout_ms: int,
        thinking: str | None = None,
        deliver: bool = False,
    ) -> dict[str, Any]:
        payload = await self.request(
            "chat.send",
            {
                "sessionKey": session_key,
                "message": message,
                "thinking": thinking,
                "deliver": deliver,
                "timeoutMs": timeout_ms,
                "idempotencyKey": idempotency_key,
            },
        )
        return payload if isinstance(payload, dict) else {}

    async def wait_run(self, run_id: str, timeout_ms: int) -> dict[str, Any]:
        payload = await self.request(
            "agent.wait",
            {"runId": run_id, "timeoutMs": timeout_ms},
        )
        return payload if isinstance(payload, dict) else {}

    async def chat_history(self, session_key: str, limit: int = 20) -> list[dict[str, Any]]:
        payload = await self.request(
            "chat.history",
            {"sessionKey": session_key, "limit": limit},
        )
        if isinstance(payload, dict):
            messages = payload.get("messages")
            if isinstance(messages, list):
                return [item for item in messages if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    async def cron_add(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.request("cron.add", params)
        return payload if isinstance(payload, dict) else {}

    async def cron_update(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        payload = await self.request("cron.update", {"jobId": job_id, "patch": patch})
        return payload if isinstance(payload, dict) else {}

    async def cron_run(self, job_id: str) -> dict[str, Any]:
        payload = await self.request("cron.run", {"jobId": job_id, "mode": "force"})
        return payload if isinstance(payload, dict) else {}

    async def sessions_list(self) -> dict[str, Any]:
        payload = await self.request("sessions.list", {})
        return payload if isinstance(payload, dict) else {}

    async def sessions_patch(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.request("sessions.patch", params)
        return payload if isinstance(payload, dict) else {}

    def _connect_params(self, nonce: str | None) -> dict[str, Any]:
        auth = {}
        if self.token:
            auth["token"] = self.token
        if self.password:
            auth["password"] = self.password
        payload = {
            "minProtocol": PROTOCOL_VERSION,
            "maxProtocol": PROTOCOL_VERSION,
            "client": {
                "id": "gateway-client",
                "displayName": "OpenTask",
                "version": self.version,
                "platform": "python",
                "mode": "backend",
            },
            "role": self.role,
            "scopes": self.scopes or ["operator.admin"],
            "caps": [],
        }
        if auth:
            payload["auth"] = auth
        return payload
