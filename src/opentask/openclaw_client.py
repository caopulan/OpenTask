from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from time import time_ns
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import json5
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
    gateway_config_path: Path | None = None
    client_id: str | None = None
    client_display_name: str | None = None
    client_mode: str | None = None
    platform: str | None = None
    device_family: str | None = None
    http_transport: httpx.AsyncBaseTransport | None = None
    _gateway_config_cache: dict[str, Any] | None = field(default=None, init=False, repr=False)

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
        if self.gateway_config_path is None:
            self.gateway_config_path = settings.gateway_config_path
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

    async def invoke_tool(
        self,
        *,
        tool: str,
        args: dict[str, Any] | None = None,
        session_key: str | None = None,
        action: str | None = None,
        timeout_ms: int = 30_000,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        shared_secret = self._resolve_http_shared_secret()
        if not shared_secret:
            raise OpenClawGatewayError(
                "gateway_http_auth_missing",
                "Gateway shared token/password required for HTTP tool invoke.",
            )

        request_payload: dict[str, Any] = {
            "tool": tool,
            "args": args or {},
        }
        if session_key:
            request_payload["sessionKey"] = session_key
        if action:
            request_payload["action"] = action

        request_headers = {
            "Authorization": f"Bearer {shared_secret}",
            "Content-Type": "application/json",
        }
        if headers:
            request_headers.update(headers)

        async with httpx.AsyncClient(
            transport=self.http_transport,
            timeout=max(timeout_ms / 1000, 5),
        ) as client:
            response = await client.post(
                self._http_base_url().rstrip("/") + "/tools/invoke",
                json=request_payload,
                headers=request_headers,
            )

        payload: dict[str, Any] | None = None
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed

        if response.status_code >= 400 or not (payload or {}).get("ok", False):
            error = payload.get("error") if isinstance(payload, dict) else {}
            if not isinstance(error, dict):
                error = {}
            raise OpenClawGatewayError(
                str(error.get("type") or f"http_{response.status_code}"),
                str(error.get("message") or f"HTTP tool invoke failed: {tool}"),
                payload,
            )

        result = payload.get("result") if payload else {}
        if isinstance(result, dict):
            details = result.get("details")
            if isinstance(details, dict):
                return details
            return result
        return {}

    async def spawn_session(
        self,
        *,
        parent_session_key: str,
        task: str,
        label: str | None = None,
        agent_id: str | None = None,
        model: str | None = None,
        thinking: str | None = None,
        cwd: str | None = None,
        timeout_seconds: int | None = None,
        mode: str = "run",
        cleanup: str = "keep",
        sandbox: str = "inherit",
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "task": task,
            "mode": mode,
            "cleanup": cleanup,
            "sandbox": sandbox,
        }
        if label:
            args["label"] = label
        if agent_id:
            args["agentId"] = agent_id
        if model:
            args["model"] = model
        if thinking:
            args["thinking"] = thinking
        if cwd:
            args["cwd"] = cwd
        if timeout_seconds is not None:
            args["runTimeoutSeconds"] = timeout_seconds
        return await self.invoke_tool(
            tool="sessions_spawn",
            args=args,
            session_key=parent_session_key,
        )

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

    def _http_base_url(self) -> str:
        parsed = urlparse(str(self.url))
        scheme = "https" if parsed.scheme == "wss" else "http"
        if not parsed.netloc:
            raise OpenClawGatewayError("invalid_gateway_url", f"Invalid gateway URL: {self.url}")
        return parsed._replace(scheme=scheme, path="", params="", query="", fragment="").geturl()

    def _resolve_http_shared_secret(self) -> str | None:
        for candidate in (self.token, self.password):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        gateway_auth = self._load_gateway_auth_from_config()
        mode = gateway_auth.get("mode")
        if mode == "password":
            password = gateway_auth.get("password")
            if isinstance(password, str) and password.strip():
                return password.strip()
        token = gateway_auth.get("token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        password = gateway_auth.get("password")
        if isinstance(password, str) and password.strip():
            return password.strip()
        return None

    def _load_gateway_auth_from_config(self) -> dict[str, Any]:
        config = self._load_gateway_config()
        gateway = config.get("gateway")
        if not isinstance(gateway, dict):
            return {}
        auth = gateway.get("auth")
        return auth if isinstance(auth, dict) else {}

    def _load_gateway_config(self) -> dict[str, Any]:
        if self._gateway_config_cache is not None:
            return self._gateway_config_cache
        path = Path(self.gateway_config_path) if self.gateway_config_path else None
        if not path or not path.exists():
            self._gateway_config_cache = {}
            return self._gateway_config_cache
        try:
            loaded = json5.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        self._gateway_config_cache = loaded if isinstance(loaded, dict) else {}
        return self._gateway_config_cache
