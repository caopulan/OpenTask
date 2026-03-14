from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    runtime_root: Path = Field(default_factory=lambda: Path.cwd() / ".opentask")
    workflows_root: Path = Field(default_factory=lambda: Path.cwd() / "workflows")
    gateway_url: str = "ws://127.0.0.1:18789"
    gateway_token: str | None = None
    gateway_password: str | None = None
    gateway_role: str = "operator"
    gateway_scopes: list[str] = Field(default_factory=lambda: ["operator.admin"])
    default_tick_timeout_ms: int = 2_000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
