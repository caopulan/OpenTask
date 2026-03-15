from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import fcntl


class RunFileLock:
    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root

    @asynccontextmanager
    async def hold(self, run_id: str) -> AsyncIterator[None]:
        path = self._lock_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+", encoding="utf-8")
        try:
            await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def _lock_path(self, run_id: str) -> Path:
        return self.runtime_root / "runs" / run_id / ".run.lock"
