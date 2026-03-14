from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import time_ns
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from websockets.asyncio.client import connect

from .config import get_settings
from .device_auth import (
    build_device_auth_payload_v3,
    load_device_auth_token,
    load_device_identity,
    public_key_raw_base64url_from_pem,
    sign_device_payload,
    store_device_auth_token,
)

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
    device_token: str | None = None
    role: str = "operator"
    scopes: list[str] | None = None
    version: str = "0.1.0"
    device_identity_path: Path | None = None
    device_auth_path: Path | None = None
    client_id: str | None = None
    client_display_name: str | None = None
    client_mode: str | None = None
    platform: str | None = None
    device_family: str | None = None

    def __post_init__(self) -> None:
        settings = get_settings()
        if self.url is None:
            self.url = settings.gateway_url
        if self.token is None:
            self.token = settings.gateway_token
        if self.password is None:
            self.password = settings.gateway_password
        if self.device_token is None:
            self.device_token = settings.gateway_device_token
        if self.scopes is None:
            self.scopes = settings.gateway_scopes
        if self.device_identity_path is None:
            self.device_identity_path = settings.gateway_device_identity_path
        if self.device_auth_path is None:
            self.device_auth_path = settings.gateway_device_auth_path
        if self.client_id is None:
            self.client_id = settings.gateway_client_id
        if self.client_display_name is None:
            self.client_display_name = settings.gateway_client_display_name
        if self.client_mode is None:
            self.client_mode = settings.gateway_client_mode
        if self.platform is None:
            self.platform = settings.gateway_platform
        if self.device_family is None:
            self.device_family = settings.gateway_device_family

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
                    self._persist_device_token(frame.get("payload"))
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
        params = {
            "sessionKey": session_key,
            "message": message,
            "deliver": deliver,
            "timeoutMs": timeout_ms,
            "idempotencyKey": idempotency_key,
        }
        if thinking is not None:
            params["thinking"] = thinking
        payload = await self.request(
            "chat.send",
            params,
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
        role = self.role
        scopes = self.scopes or ["operator.admin"]
        gateway_token = self.token.strip() if self.token else None
        gateway_password = self.password.strip() if self.password else None
        explicit_device_token = self.device_token.strip() if self.device_token else None
        device_identity = self._load_device_identity() if self._should_attach_device_identity() else None
        stored_device_token = (
            load_device_auth_token(Path(self.device_auth_path), device_id=device_identity.device_id, role=role)
            if device_identity and self.device_auth_path
            else None
        )
        resolved_device_token = explicit_device_token or (
            stored_device_token if not (gateway_token or gateway_password) else None
        )
        auth = {}
        if gateway_token or resolved_device_token:
            auth["token"] = gateway_token or resolved_device_token
        if resolved_device_token:
            auth["deviceToken"] = resolved_device_token
        if gateway_password:
            auth["password"] = gateway_password
        signed_at_ms = time_ns() // 1_000_000
        device = None
        if device_identity:
            payload = build_device_auth_payload_v3(
                device_id=device_identity.device_id,
                client_id=self.client_id or "gateway-client",
                client_mode=self.client_mode or "backend",
                role=role,
                scopes=scopes,
                signed_at_ms=signed_at_ms,
                token=(gateway_token or resolved_device_token),
                nonce=nonce or "",
                platform=self.platform,
                device_family=self.device_family,
            )
            device = {
                "id": device_identity.device_id,
                "publicKey": public_key_raw_base64url_from_pem(device_identity.public_key_pem),
                "signature": sign_device_payload(device_identity.private_key_pem, payload),
                "signedAt": signed_at_ms,
                "nonce": nonce,
            }
        payload = {
            "minProtocol": PROTOCOL_VERSION,
            "maxProtocol": PROTOCOL_VERSION,
            "client": {
                "id": self.client_id or "gateway-client",
                "displayName": self.client_display_name or "OpenTask",
                "version": self.version,
                "platform": self.platform or "python",
                "deviceFamily": self.device_family,
                "mode": self.client_mode or "backend",
            },
            "role": role,
            "scopes": scopes,
            "caps": [],
        }
        if auth:
            payload["auth"] = auth
        if device:
            payload["device"] = device
        return payload

    def _load_device_identity(self):
        if not self.device_identity_path:
            return None
        return load_device_identity(Path(self.device_identity_path))

    def _should_attach_device_identity(self) -> bool:
        if not (self.token or self.password):
            return True
        try:
            hostname = (urlparse(str(self.url)).hostname or "").lower()
        except ValueError:
            return True
        return hostname not in {"127.0.0.1", "::1", "localhost"}

    def _persist_device_token(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        auth = payload.get("auth")
        device_identity = self._load_device_identity()
        if not isinstance(auth, dict) or not device_identity or not self.device_auth_path:
            return
        token = auth.get("deviceToken")
        role = auth.get("role")
        scopes = auth.get("scopes")
        if not isinstance(token, str) or not token.strip():
            return
        store_device_auth_token(
            Path(self.device_auth_path),
            device_id=device_identity.device_id,
            role=role if isinstance(role, str) and role else self.role,
            token=token.strip(),
            scopes=[item for item in scopes if isinstance(item, str)] if isinstance(scopes, list) else None,
        )
