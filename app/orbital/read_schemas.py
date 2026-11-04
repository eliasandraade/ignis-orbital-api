"""Public read contracts for persisted detections (Sprint 1.3).

Everything here comes from PostgreSQL: no response is built from a live call
to NASA or INPE, and `persisted` is true only because every item is a row of
orbital_detections.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

THERMAL_ANOMALY_DISCLAIMER = (
    "Focos de calor são anomalias térmicas detectadas por satélite. Não confirmam "
    "incêndio: exigem validação por operador humano."
)

# State of one source (or product), from ingestion_runs:
# live: last run ok and recent · stale: last ok run older than the threshold ·
# degraded: some products ok, others failing · unavailable: last attempt failed ·
# disabled: not configured (e.g. no NASA key) · never_ingested: no run yet.
SourceState = Literal["live", "stale", "degraded", "unavailable", "disabled", "never_ingested"]


class JurisdictionRef(BaseModel):
    ibge_code: str
    name: str


class Detection(BaseModel):
    id: uuid.UUID
    source: str
    product: str
    satellite: str
    instrument: str
    observed_at: datetime  # when the satellite saw it (UTC)
    ingested_at: datetime  # when IGNIS stored it (UTC)
    lat: float
    lng: float
    jurisdiction: JurisdictionRef
    confidence: Literal["low", "nominal", "high"] | None  # VIIRS class
    confidence_pct: int | None  # MODIS 0-100 %
    frp_mw: float | None
    brightness_k: float | None
    brightness_channel: Literal["VIIRS_I4", "MODIS_21_22"] | None
    daynight: Literal["D", "N"] | None
    provider_record_id: str | None
    ingestion_run_id: uuid.UUID
    persisted: Literal[True] = True


class DetectionDetail(Detection):
    raw: dict  # the provider's row, verbatim


class ProductStatus(BaseModel):
    product: str
    state: SourceState
    last_attempt_at: datetime | None
    last_attempt_status: str | None
    last_error_code: str | None
    last_success_at: datetime | None
    running: bool
    origin: Literal["live", "fixture"] | None  # fixture: historical public sample


class SourceStatus(BaseModel):
    source: str
    label: str
    state: SourceState
    message: str
    last_success_at: datetime | None  # when IGNIS last fetched it successfully
    latest_observation_at: datetime | None  # newest detection stored (satellite time)
    stale_after_minutes: int
    origin: Literal["live", "fixture"] | None
    products: list[ProductStatus]


class AppliedFilters(BaseModel):
    observed_from: datetime
    observed_to: datetime
    source: str | None
    satellite: str | None
    jurisdiction: str | None
    bbox: list[float] | None


class DetectionPage(BaseModel):
    items: list[Detection]
    total: int
    page: int
    size: int
    pages: int
    truncated: bool  # total > page * size: more detections than returned
    filters: AppliedFilters
    sources: list[SourceStatus]
    persisted: Literal[True] = True
    data_origin: Literal["postgis"] = "postgis"
    disclaimer: str = THERMAL_ANOMALY_DISCLAIMER


class CountBucket(BaseModel):
    key: str
    count: int


class DayBucket(BaseModel):
    day: str  # YYYY-MM-DD (UTC)
    count: int


class MunicipalityCount(BaseModel):
    ibge_code: str
    name: str
    count: int


class DetectionStats(BaseModel):
    filters: AppliedFilters
    total: int
    municipalities_with_detections: int
    by_source: list[CountBucket]
    by_satellite: list[CountBucket]
    by_day: list[DayBucket]
    top_municipalities: list[MunicipalityCount]
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    last_ingested_at: datetime | None
    sources: list[SourceStatus]
    disclaimer: str = THERMAL_ANOMALY_DISCLAIMER


class DatasetRef(BaseModel):
    source: str
    product: str
    version: str
    reference_date: str
    content_sha256: str


class MunicipalitySummary(BaseModel):
    ibge_code: str
    name: str
    official_area_km2: float
    detections: int


class MunicipalityList(BaseModel):
    items: list[MunicipalitySummary]
    total: int
    dataset: DatasetRef
    filters: AppliedFilters
