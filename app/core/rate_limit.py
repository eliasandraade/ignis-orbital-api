"""Minimal fixed-window rate limiter for public and authentication endpoints.

State is in-memory and per process: with N uvicorn workers the effective limit
is up to N times the configured value. It is a first line of defence against
brute force and abuse of upstream providers (Nominatim, NASA), not a
replacement for an edge/WAF limiter or a shared store (Redis) — see
docs/IGNIS/SECURITY-REVIEW.md.
"""

import time
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.config import get_settings

_MAX_TRACKED_KEYS = 10_000

# key -> (window_start, count)
_windows: dict[str, tuple[float, int]] = {}


def client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy_headers and settings.client_ip_header == "x-real-ip":
        # Railway's edge overwrites X-Real-IP on every request, so a client copy
        # never reaches the app. Its X-Forwarded-For hop count is not fixed:
        # the rightmost entry may be an internal proxy shared by all clients.
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
    elif settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        # Rightmost entry is appended by the trusted proxy; leftmost ones are
        # client-controlled and can be spoofed.
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def _hit(key: str, limit: int, window_seconds: int, now: float) -> int | None:
    """Register a hit. Returns seconds to wait when the limit is exceeded."""
    start, count = _windows.get(key, (now, 0))
    if now - start >= window_seconds:
        start, count = now, 0
    count += 1
    if len(_windows) >= _MAX_TRACKED_KEYS and key not in _windows:
        _evict_expired(now, window_seconds)
    _windows[key] = (start, count)
    if count > limit:
        return max(1, int(window_seconds - (now - start)))
    return None


def _evict_expired(now: float, window_seconds: int) -> None:
    # list() is required: entries are deleted while iterating.
    for k, (start, _count) in list(_windows.items()):  # NOSONAR python:S7504
        if now - start >= window_seconds:
            del _windows[k]
    if len(_windows) >= _MAX_TRACKED_KEYS:
        _windows.clear()


def rate_limit(scope: str, limit: int, window_seconds: int = 60) -> Callable:
    """FastAPI dependency: allow `limit` requests per client IP per window."""

    # Deliberately async without await: FastAPI runs sync dependencies in a
    # thread pool, which would make the shared counter dict racy. As a
    # coroutine it always runs on the single event-loop thread.
    async def _check(request: Request) -> None:  # NOSONAR python:S7503
        if not get_settings().rate_limit_enabled:
            return
        retry_after = _hit(f"{scope}:{client_ip(request)}", limit, window_seconds, time.monotonic())
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Muitas requisições. Tente novamente em instantes.",
                headers={"Retry-After": str(retry_after)},
            )

    return _check


def reset_rate_limits() -> None:
    """Clear all counters (used in tests)."""
    _windows.clear()
