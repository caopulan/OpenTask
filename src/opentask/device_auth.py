from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


@dataclass(slots=True)
class DeviceIdentity:
    device_id: str
    public_key_pem: str
    private_key_pem: str


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def base64url_decode(value: str) -> bytes:
    padded = value + "=" * ((4 - (len(value) % 4)) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def normalize_device_metadata_for_auth(value: str | None) -> str:
    if not value:
        return ""
    trimmed = value.strip()
    return "".join(chr(ord(char) + 32) if "A" <= char <= "Z" else char for char in trimmed)


def build_device_auth_payload_v3(
    *,
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str | None,
    nonce: str,
    platform: str | None,
    device_family: str | None,
) -> str:
    return "|".join(
        [
            "v3",
            device_id,
            client_id,
            client_mode,
            role,
            ",".join(scopes),
            str(signed_at_ms),
            token or "",
            nonce,
            normalize_device_metadata_for_auth(platform),
            normalize_device_metadata_for_auth(device_family),
        ]
    )


def load_device_identity(path: Path) -> DeviceIdentity | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    device_id = payload.get("deviceId")
    public_key_pem = payload.get("publicKeyPem")
    private_key_pem = payload.get("privateKeyPem")
    if not all(isinstance(value, str) and value for value in (device_id, public_key_pem, private_key_pem)):
        return None
    return DeviceIdentity(
        device_id=device_id,
        public_key_pem=public_key_pem,
        private_key_pem=private_key_pem,
    )


def load_device_auth_token(path: Path, *, device_id: str, role: str) -> str | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("deviceId") != device_id:
        return None
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    entry = tokens.get(role)
    if not isinstance(entry, dict):
        return None
    token = entry.get("token")
    return token if isinstance(token, str) and token.strip() else None


def store_device_auth_token(
    path: Path,
    *,
    device_id: str,
    role: str,
    token: str,
    scopes: list[str] | None = None,
) -> None:
    payload: dict = {"version": 1, "deviceId": device_id, "tokens": {}}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(current, dict):
                payload.update(current)
        except json.JSONDecodeError:
            pass
    payload["deviceId"] = device_id
    tokens = payload.setdefault("tokens", {})
    if not isinstance(tokens, dict):
        tokens = {}
        payload["tokens"] = tokens
    tokens[role] = {
        "token": token,
        "role": role,
        "scopes": scopes or [],
        "updatedAtMs": __import__("time").time_ns() // 1_000_000,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def public_key_raw_base64url_from_pem(public_key_pem: str) -> str:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("device public key must be Ed25519")
    return base64url_encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def derive_device_id_from_public_key(public_key_pem: str) -> str:
    raw = base64url_decode(public_key_raw_base64url_from_pem(public_key_pem))
    return hashlib.sha256(raw).hexdigest()


def sign_device_payload(private_key_pem: str, payload: str) -> str:
    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("device private key must be Ed25519")
    return base64url_encode(private_key.sign(payload.encode("utf-8")))


def verify_device_signature(public_key_pem: str, payload: str, signature: str) -> bool:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(public_key, Ed25519PublicKey):
        return False
    try:
        public_key.verify(base64url_decode(signature), payload.encode("utf-8"))
    except Exception:
        return False
    return True
