"""HTTP plumbing shared by the detection providers.

Failures surface only as stable codes (ProviderHttpError.code): an httpx
exception's text carries the request URL, and the FIRMS URL carries the
MAP_KEY, so it is never chained, logged or stored.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

import httpx

# httpx logs every request URL at INFO; a FIRMS URL contains the MAP_KEY.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

USER_AGENT = "IGNIS-Orbital/1.2 (+https://github.com/eliasandraade/ignis-orbital-api)"
Sleep = Callable[[float], Awaitable[None]]


class ProviderHttpError(Exception):
    """Transport-level failure after retries; `code` is safe to store and log."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 2.0  # 2 s, 4 s, ... (exponential)
    max_delay: float = 60.0  # also caps a server's Retry-After

    def delay(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after and retry_after.strip().isdigit():
            return min(float(retry_after), self.max_delay)
        return min(self.base_delay * 2 ** (attempt - 1), self.max_delay)


class RequestSpacer:
    """Keeps a minimum interval between requests to one provider."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ):
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            if self._last is not None:
                remaining = self._min_interval - (self._clock() - self._last)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last = self._clock()


RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


async def get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    policy: RetryPolicy,
    spacer: RequestSpacer,
    headers: dict[str, str] | None = None,
    sleep: Sleep = asyncio.sleep,
) -> httpx.Response:
    """GET with bounded retries on timeouts, connection errors, 429 and 5xx.

    Any other status (200, 304, 4xx) is returned for the caller to interpret.
    Raises ProviderHttpError when every attempt failed.
    """
    code = "unknown"
    for attempt in range(1, policy.attempts + 1):
        await spacer.wait()
        retry_after = None
        try:
            response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            code = "timeout"
        except httpx.TransportError:
            code = "connection_error"
        else:
            if response.status_code not in RETRYABLE_STATUS:
                return response
            code = (
                "rate_limited" if response.status_code == 429 else (f"http_{response.status_code}")
            )
            retry_after = response.headers.get("retry-after")
        if attempt < policy.attempts:
            await sleep(policy.delay(attempt, retry_after))
    raise ProviderHttpError(code)


class RedactSecrets(logging.Filter):
    """Replaces configured secret values in every record passing a handler."""

    def __init__(self, secrets: Iterable[str]):
        super().__init__()
        self._secrets = [s for s in secrets if s and len(s) >= 6]

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets:
            message = record.getMessage()
            for secret in self._secrets:
                message = message.replace(secret, "***")
            record.msg, record.args = message, None
        return True
