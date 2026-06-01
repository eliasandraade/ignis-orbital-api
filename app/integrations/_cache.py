"""In-memory TTL cache shared by all external API integrations.

Stores responses so external APIs are not called on every request.
Each entry expires after its individual TTL; expired entries are evicted on read.
"""

import time
from typing import Any

_store: dict[str, tuple[Any, float]] = {}


def cache_get(key: str) -> Any | None:
    entry = _store.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() < expires_at:
        return value
    del _store[key]
    return None


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    _store[key] = (value, time.monotonic() + ttl_seconds)


def cache_clear() -> None:
    """Clear all cache entries (used in tests)."""
    _store.clear()
