"""Contracts between detection providers (NASA FIRMS, INPE) and persistence.

A provider (Sprint 1.2) fetches one time window for the Ceará bounding box and
returns NormalizedDetection objects plus the number of source rows it had to
reject. app.orbital.repository stores them; nothing else writes detections.

Invariants a provider can rely on:
- dedup_key is deterministic: re-fetching the same window stores nothing new;
- detections outside the official Ceará municipal boundaries are counted as
  out of scope and not stored (the bounding box only narrows the request);
- no provider ever fabricates data: on failure it returns a status and zero
  detections, never placeholders.
"""

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal, Protocol


class DetectionSource(StrEnum):
    NASA_FIRMS = "NASA_FIRMS"
    INPE_QUEIMADAS = "INPE_QUEIMADAS"


class RunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"  # every requested product answered and was stored
    PARTIAL = "partial"  # some products failed; what was stored is consistent
    UNAVAILABLE = "unavailable"  # provider unreachable or answered garbage
    DISABLED = "disabled"  # provider not configured (e.g. missing API key)
    ERROR = "error"  # our failure, or a run abandoned without finishing


FINAL_STATUSES = frozenset(RunStatus) - {RunStatus.RUNNING}

Trigger = Literal["schedule", "manual"]
Confidence = Literal["low", "nominal", "high"]
DayNight = Literal["D", "N"]

# Request envelope only (lon_min, lat_min, lon_max, lat_max), slightly larger
# than the IBGE 2025 extent of Ceará. The official polygons decide scope.
CEARA_BBOX = (-41.5, -7.9, -37.2, -2.7)

# Fixed forever: changing it would change every dedup_key already stored.
DEDUP_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "urn:ignis:orbital-detection:v1")
DEDUP_COORD_DECIMALS = 4  # ~11 m: tolerates re-serialisation, not distinct pixels


class InvalidDetectionError(ValueError):
    """A provider produced a record that violates the contract."""


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        for value in (self.start, self.end):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("TimeWindow exige datetimes com fuso horário")
        if self.end <= self.start:
            raise ValueError("TimeWindow.end deve ser posterior a start")

    @classmethod
    def last(cls, duration: timedelta, now: datetime | None = None) -> "TimeWindow":
        end = now or datetime.now(UTC)
        return cls(start=end - duration, end=end)


def _coord_key(value: float) -> str:
    text = f"{value:.{DEDUP_COORD_DECIMALS}f}"
    return "0.0000" if text == "-0.0000" else text


def compute_dedup_key(
    source: str, satellite: str, observed_at: datetime, latitude: float, longitude: float
) -> uuid.UUID:
    """Natural key of one observation: same pass, same pixel → same key.

    The product (NRT vs. standard processing) is deliberately not part of the
    key, so a reprocessed copy of an observation is recognised as a duplicate.
    """
    instant = observed_at.astimezone(UTC).replace(microsecond=0).isoformat()
    name = "|".join(
        (source, satellite.upper(), instant, _coord_key(latitude), _coord_key(longitude))
    )
    return uuid.uuid5(DEDUP_NAMESPACE, name)


@dataclass(frozen=True, slots=True)
class NormalizedDetection:
    source: DetectionSource
    product: str  # provider product id, e.g. "VIIRS_SNPP_NRT"
    satellite: str  # e.g. "N20", "Aqua"
    instrument: str  # e.g. "VIIRS", "MODIS"
    observed_at: datetime  # acquisition instant, timezone-aware
    latitude: float
    longitude: float
    confidence: Confidence | None = None
    frp_mw: float | None = None
    brightness_k: float | None = None
    daynight: DayNight | None = None
    # The source row as received (no secrets: providers strip request URLs/keys).
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source, DetectionSource):
            raise InvalidDetectionError(f"fonte desconhecida: {self.source!r}")
        for name in ("product", "satellite", "instrument"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 64:
                raise InvalidDetectionError(f"{name} inválido: {value!r}")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise InvalidDetectionError("observed_at sem fuso horário")
        if not (math.isfinite(self.latitude) and -90 <= self.latitude <= 90):
            raise InvalidDetectionError(f"latitude fora do intervalo: {self.latitude!r}")
        if not (math.isfinite(self.longitude) and -180 <= self.longitude <= 180):
            raise InvalidDetectionError(f"longitude fora do intervalo: {self.longitude!r}")
        if self.confidence not in (None, "low", "nominal", "high"):
            raise InvalidDetectionError(f"confidence inválida: {self.confidence!r}")
        if self.daynight not in (None, "D", "N"):
            raise InvalidDetectionError(f"daynight inválido: {self.daynight!r}")
        if self.frp_mw is not None and not (math.isfinite(self.frp_mw) and self.frp_mw >= 0):
            raise InvalidDetectionError(f"frp_mw inválido: {self.frp_mw!r}")
        if self.brightness_k is not None and not (
            math.isfinite(self.brightness_k) and self.brightness_k > 0
        ):
            raise InvalidDetectionError(f"brightness_k inválido: {self.brightness_k!r}")

    @property
    def dedup_key(self) -> uuid.UUID:
        return compute_dedup_key(
            self.source, self.satellite, self.observed_at, self.latitude, self.longitude
        )


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """What one provider call produced for one product."""

    product: str
    status: Literal["ok", "unavailable", "disabled"]
    detections: tuple[NormalizedDetection, ...] = ()
    rejected: int = 0  # source rows that failed validation (counted, not stored)
    error_code: str | None = None  # stable, secret-free, e.g. "http_503"

    def __post_init__(self) -> None:
        if self.rejected < 0:
            raise ValueError("rejected não pode ser negativo")
        if self.status != "ok" and self.detections:
            raise ValueError("um resultado sem sucesso não carrega detecções")


class DetectionProvider(Protocol):
    """Implemented in Sprint 1.2 by the FIRMS and INPE clients."""

    source: DetectionSource

    def products(self) -> tuple[str, ...]: ...

    async def fetch(
        self, product: str, window: TimeWindow, bbox: tuple[float, float, float, float]
    ) -> ProviderResult: ...
