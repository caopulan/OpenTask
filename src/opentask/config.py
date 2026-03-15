from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _default_gateway_state_dir() -> Path:
    return Path(_env_first("OPENTASK_GATEWAY_STATE_DIR", "OPENCLAW_STATE_DIR") or "~/.openclaw").expanduser()


def _default_gateway_config_path() -> Path:
    return Path(
        _env_first("OPENTASK_GATEWAY_CONFIG_PATH", "OPENCLAW_CONFIG_PATH")
        or (_default_gateway_state_dir() / "openclaw.json")
    ).expanduser()


def _default_gateway_scopes() -> list[str]:
    raw = _env_first("OPENTASK_GATEWAY_SCOPES")
    if not raw:
        return ["operator.admin"]
    scopes = [item.strip() for item in raw.split(",") if item.strip()]
    return scopes or ["operator.admin"]


class Settings(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    runtime_root: Path = Field(default_factory=lambda: Path.cwd() / ".opentask")
    workflows_root: Path = Field(default_factory=lambda: Path.cwd() / "workflows")
    opentask_agent_id: str = Field(default_factory=lambda: _env_first("OPENTASK_AGENT_ID") or "opentask")
    gateway_url: str = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_URL", "OPENCLAW_GATEWAY_URL") or "ws://127.0.0.1:18789")
    gateway_token: str | None = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_TOKEN", "OPENCLAW_GATEWAY_TOKEN"))
    gateway_password: str | None = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_PASSWORD", "OPENCLAW_GATEWAY_PASSWORD"))
    gateway_device_token: str | None = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_DEVICE_TOKEN"))
    gateway_role: str = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_ROLE") or "operator")
    gateway_scopes: list[str] = Field(default_factory=_default_gateway_scopes)
    gateway_state_dir: Path = Field(default_factory=_default_gateway_state_dir)
    gateway_config_path: Path = Field(default_factory=_default_gateway_config_path)
    gateway_device_identity_path: Path = Field(
        default_factory=lambda: Path(
            _env_first("OPENTASK_GATEWAY_DEVICE_IDENTITY_PATH")
            or (_default_gateway_state_dir() / "identity" / "device.json")
        ).expanduser()
    )
    gateway_device_auth_path: Path = Field(
        default_factory=lambda: Path(
            _env_first("OPENTASK_GATEWAY_DEVICE_AUTH_PATH")
            or (_default_gateway_state_dir() / "identity" / "device-auth.json")
        ).expanduser()
    )
    gateway_client_id: str = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_CLIENT_ID") or "gateway-client")
    gateway_client_display_name: str = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_CLIENT_DISPLAY_NAME") or "OpenTask")
    gateway_client_mode: str = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_CLIENT_MODE") or "backend")
    gateway_platform: str = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_PLATFORM") or sys.platform)
    gateway_device_family: str = Field(default_factory=lambda: _env_first("OPENTASK_GATEWAY_DEVICE_FAMILY") or "desktop")
    default_tick_timeout_ms: int = 2_000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
