from __future__ import annotations

import json
from pathlib import Path

import pytest
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from websockets.asyncio.server import serve

from opentask.device_auth import (
    build_device_auth_payload_v3,
    derive_device_id_from_public_key,
    public_key_raw_base64url_from_pem,
    verify_device_signature,
)
from opentask.openclaw_client import OpenClawClient
from opentask.openclaw_client import OpenClawGatewayError


def write_identity_files(root: Path) -> tuple[Path, Path, str, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    device_id = derive_device_id_from_public_key(public_pem)
    identity_path = root / "device.json"
    auth_path = root / "device-auth.json"
    identity_path.write_text(
        json.dumps(
            {
                "version": 1,
                "deviceId": device_id,
                "publicKeyPem": public_pem,
                "privateKeyPem": private_pem,
                "createdAtMs": 1,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    auth_path.write_text(
        json.dumps(
            {
                "version": 1,
                "deviceId": device_id,
                "tokens": {
                    "operator": {
                        "token": "stored-device-token",
                        "role": "operator",
                        "scopes": ["operator.admin"],
                        "updatedAtMs": 1,
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return identity_path, auth_path, public_pem, device_id


@pytest.mark.asyncio
async def test_openclaw_client_sends_device_auth_payload(tmp_path: Path) -> None:
    identity_path, auth_path, public_pem, device_id = write_identity_files(tmp_path)
    captured: list[dict] = []

    async def handler(websocket) -> None:
        await websocket.send(
            json.dumps({"type": "event", "event": "connect.challenge", "payload": {"nonce": "nonce-123"}})
        )
        connect_frame = json.loads(await websocket.recv())
        captured.append(connect_frame)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect_frame["id"],
                    "ok": True,
                    "payload": {
                        "auth": {
                            "deviceToken": "rotated-device-token",
                            "role": "operator",
                            "scopes": ["operator.admin"],
                        }
                    },
                }
            )
        )
        request_frame = json.loads(await websocket.recv())
        await websocket.send(
            json.dumps({"type": "res", "id": request_frame["id"], "ok": True, "payload": {"status": "ok"}})
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(
            url=f"ws://127.0.0.1:{port}",
            device_identity_path=identity_path,
            device_auth_path=auth_path,
            version="test",
            platform="darwin",
            device_family="desktop",
        )
        payload = await client.request("sessions.list", {})
        assert payload == {"status": "ok"}

    connect_params = captured[0]["params"]
    assert connect_params["auth"]["token"] == "stored-device-token"
    assert connect_params["auth"]["deviceToken"] == "stored-device-token"
    assert connect_params["device"]["id"] == device_id
    assert connect_params["device"]["publicKey"] == public_key_raw_base64url_from_pem(public_pem)

    signature_payload = build_device_auth_payload_v3(
        device_id=device_id,
        client_id="gateway-client",
        client_mode="backend",
        role="operator",
        scopes=["operator.admin"],
        signed_at_ms=connect_params["device"]["signedAt"],
        token="stored-device-token",
        nonce="nonce-123",
        platform="darwin",
        device_family="desktop",
    )
    assert verify_device_signature(public_pem, signature_payload, connect_params["device"]["signature"])

    persisted = json.loads(auth_path.read_text(encoding="utf-8"))
    assert persisted["tokens"]["operator"]["token"] == "rotated-device-token"


@pytest.mark.asyncio
async def test_openclaw_client_omits_device_identity_for_loopback_shared_token(tmp_path: Path) -> None:
    identity_path, auth_path, _, _ = write_identity_files(tmp_path)
    captured: list[dict] = []

    async def handler(websocket) -> None:
        await websocket.send(
            json.dumps({"type": "event", "event": "connect.challenge", "payload": {"nonce": "nonce-123"}})
        )
        connect_frame = json.loads(await websocket.recv())
        captured.append(connect_frame)
        await websocket.send(json.dumps({"type": "res", "id": connect_frame["id"], "ok": True, "payload": {}}))
        request_frame = json.loads(await websocket.recv())
        await websocket.send(
            json.dumps({"type": "res", "id": request_frame["id"], "ok": True, "payload": {"status": "ok"}})
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(
            url=f"ws://127.0.0.1:{port}",
            token="shared-token",
            device_identity_path=identity_path,
            device_auth_path=auth_path,
            version="test",
        )
        payload = await client.request("sessions.list", {})
        assert payload == {"status": "ok"}

    connect_params = captured[0]["params"]
    assert connect_params["auth"]["token"] == "shared-token"
    assert "deviceToken" not in connect_params["auth"]
    assert "device" not in connect_params


@pytest.mark.asyncio
async def test_openclaw_client_invokes_sessions_spawn_over_http(tmp_path: Path) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        """{
  // shared secret for HTTP tool invoke
  gateway: {
    auth: {
      mode: "token",
      token: "config-token",
    },
  },
}
""",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "details": {
                        "status": "accepted",
                        "runId": "spawn-run-1",
                        "childSessionKey": "agent:main:subagent:child-1",
                    }
                },
            },
        )

    client = OpenClawClient(
        url="ws://127.0.0.1:18789",
        gateway_config_path=config_path,
        http_transport=httpx.MockTransport(handler),
    )
    payload = await client.spawn_session(
        parent_session_key="agent:main:main",
        task="Delegate work",
        label="Delegate",
        cwd="/tmp/demo",
        timeout_seconds=30,
    )

    assert payload["status"] == "accepted"
    assert payload["childSessionKey"] == "agent:main:subagent:child-1"
    assert captured["url"] == "http://127.0.0.1:18789/tools/invoke"
    assert captured["auth"] == "Bearer config-token"
    assert captured["body"] == {
        "tool": "sessions_spawn",
        "args": {
            "task": "Delegate work",
            "mode": "run",
            "cleanup": "keep",
            "sandbox": "inherit",
            "label": "Delegate",
            "cwd": "/tmp/demo",
            "runTimeoutSeconds": 30,
        },
        "sessionKey": "agent:main:main",
    }


@pytest.mark.asyncio
async def test_openclaw_client_wraps_transport_disconnects(tmp_path: Path) -> None:
    identity_path, auth_path, _, _ = write_identity_files(tmp_path)

    async def handler(websocket) -> None:
        await websocket.send(
            json.dumps({"type": "event", "event": "connect.challenge", "payload": {"nonce": "nonce-123"}})
        )
        connect_frame = json.loads(await websocket.recv())
        await websocket.send(json.dumps({"type": "res", "id": connect_frame["id"], "ok": True, "payload": {}}))
        await websocket.close()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = OpenClawClient(
            url=f"ws://127.0.0.1:{port}",
            device_identity_path=identity_path,
            device_auth_path=auth_path,
            version="test",
        )
        with pytest.raises(OpenClawGatewayError) as excinfo:
            await client.request("sessions.list", {})

    assert excinfo.value.code == "transport_error"
