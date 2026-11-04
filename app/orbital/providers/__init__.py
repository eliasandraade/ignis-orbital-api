"""Detection providers: NASA FIRMS and INPE Programa Queimadas."""

import httpx

from app.orbital.contracts import DetectionProvider
from app.orbital.providers._http import RequestSpacer, RetryPolicy
from app.orbital.providers.firms import FirmsProvider
from app.orbital.providers.inpe import InpeProvider

SOURCES = ("firms", "inpe")


def providers_from_settings(
    settings,
    *,
    sources: tuple[str, ...] = SOURCES,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[DetectionProvider]:
    """Both providers are always returned when selected: without a MAP_KEY the
    FIRMS one reports 'disabled' runs instead of disappearing silently."""
    policy = RetryPolicy(attempts=settings.ingest_http_attempts)
    interval = settings.ingest_min_request_interval_seconds
    providers: list[DetectionProvider] = []
    if "firms" in sources:
        providers.append(
            FirmsProvider(
                settings.nasa_firms_map_key,
                base_url=settings.nasa_firms_base_url,
                timeout=settings.ingest_http_timeout_seconds,
                policy=policy,
                spacer=RequestSpacer(interval),
                transport=transport,
            )
        )
    if "inpe" in sources:
        providers.append(
            InpeProvider(
                enabled=settings.inpe_queimadas_enabled,
                base_url=settings.inpe_queimadas_base_url,
                timeout=settings.ingest_http_timeout_seconds,
                policy=policy,
                spacer=RequestSpacer(interval),
                transport=transport,
            )
        )
    return providers
