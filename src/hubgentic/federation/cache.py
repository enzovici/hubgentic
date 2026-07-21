"""In-memory, TTL-bounded request cache.

Serves explain_lineage(request_id) for recently produced unified entities.
Nothing is persisted — "nothing at rest" means no disk, not no working memory.
"""
from __future__ import annotations

import time
from typing import Any


class RequestCache:
    def __init__(self, ttl_seconds: float = 900.0) -> None:
        self._ttl = ttl_seconds
        self._items: dict[str, tuple[float, Any]] = {}

    def put(self, key: str, value: Any) -> None:
        self._prune()
        self._items[key] = (time.monotonic() + self._ttl, value)

    def get(self, key: str) -> Any | None:
        self._prune()
        item = self._items.get(key)
        return item[1] if item is not None else None

    def _prune(self) -> None:
        now = time.monotonic()
        self._items = {k: v for k, v in self._items.items() if v[0] > now}
