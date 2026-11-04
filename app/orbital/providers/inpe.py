"""INPE Programa Queimadas — daily open-data CSV → NormalizedDetection.

Interface choice (Sprint 1.2): the daily CSV files of the INPE open-data
server, not the TerraBrasilis WFS:
- the CSVs are the product listed on INPE's open-data page (10 min, daily,
  monthly, yearly); the WFS is not, and the WFS layer used by the old PR #2
  (ams1h:active-fire-today) no longer exists;
- each file has a stable dated name, Last-Modified and ETag: a run records
  exactly which file versions it read (name, ETag, SHA-256) and repeats the
  request conditionally, so an unchanged file is not downloaded again;
- the daily file carries INPE's own focus id (`id`, same UUID as the WFS
  `foco_id`) and an explicit GMT timestamp (`data_hora_gmt`).

File: {base}/focos_diario_br_YYYYMMDD.csv (UTC day of data_hora_gmt). INPE
rewrites the current day's file several times a day. Columns observed on
2026-11-03: id, lat, lon, data_hora_gmt, satelite, municipio, estado, pais,
municipio_id, estado_id, pais_id, numero_dias_sem_chuva, precipitacao,
risco_fogo, bioma, frp.

Not inferred: INPE publishes no confidence, no brightness and no documented
FRP unit in this file, so confidence/brightness/frp_mw stay empty and the
original values remain in `raw`. Rows outside the request bbox are skipped
before validation (the file covers all of Brazil) and reported in provenance.
"""

import asyncio
import csv
import hashlib
import io
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.orbital.contracts import (
    BBox,
    DetectionSource,
    InvalidDetectionError,
    NormalizedDetection,
    ProviderResult,
    TimeWindow,
)
from app.orbital.providers._http import (
    USER_AGENT,
    ProviderHttpError,
    RequestSpacer,
    RetryPolicy,
    Sleep,
    get_with_retries,
)

PRODUCT = "FOCOS_DIARIO_BR"
REQUIRED_COLUMNS = frozenset({"id", "lat", "lon", "data_hora_gmt", "satelite"})
MAX_DAYS = 3

# Sensor carried by each satellite as named by INPE. A satellite missing here
# is still ingested, with instrument "UNSPECIFIED" (nothing is guessed).
INSTRUMENTS = {
    "AQUA_M-T": "MODIS",
    "AQUA_M-M": "MODIS",
    "TERRA_M-T": "MODIS",
    "TERRA_M-M": "MODIS",
    "NPP-375": "VIIRS",
    "NPP-375D": "VIIRS",
    "NOAA-20": "VIIRS",
    "NOAA-21": "VIIRS",
    "GOES-16": "ABI",
    "GOES-19": "ABI",
    "METOP-B": "AVHRR",
    "METOP-C": "AVHRR",
    "MSG-03": "SEVIRI",
}


class RowError(ValueError):
    """One CSV row violates the documented format (counted as rejected)."""


def _coordinate(row: Mapping[str, str], column: str) -> float:
    try:
        value = float((row.get(column) or "").strip())
    except ValueError as exc:
        raise RowError(f"{column} inválida") from exc
    if not math.isfinite(value):
        raise RowError(f"{column} não finita")
    return value


def parse_row(row: Mapping[str, str], latitude: float, longitude: float) -> NormalizedDetection:
    satellite = (row.get("satelite") or "").strip()
    try:
        observed_at = datetime.strptime(
            (row.get("data_hora_gmt") or "").strip(), "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=UTC)
    except ValueError as exc:
        raise RowError("data_hora_gmt inválida") from exc
    record_id = (row.get("id") or "").strip()
    try:
        return NormalizedDetection(
            source=DetectionSource.INPE_QUEIMADAS,
            product=PRODUCT,
            satellite=satellite,
            instrument=INSTRUMENTS.get(satellite.upper(), "UNSPECIFIED"),
            observed_at=observed_at,
            latitude=latitude,
            longitude=longitude,
            provider_record_id=record_id or None,
            raw={k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()},
        )
    except InvalidDetectionError as exc:
        raise RowError(str(exc)) from exc


def file_names(window: TimeWindow) -> list[tuple[str, bool]]:
    """(file name, is_current_day) for every UTC day of the window, newest last."""
    first = window.start.astimezone(UTC).date()
    last = window.end.astimezone(UTC).date()
    first = max(first, last - timedelta(days=MAX_DAYS - 1))
    today = datetime.now(UTC).date()
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return [(f"focos_diario_br_{d:%Y%m%d}.csv", d >= today) for d in days]


def _inside(bbox: BBox, latitude: float, longitude: float) -> bool:
    west, south, east, north = bbox
    return west <= longitude <= east and south <= latitude <= north


class InpeProvider:
    source = DetectionSource.INPE_QUEIMADAS

    def __init__(
        self,
        *,
        enabled: bool = True,
        base_url: str = (
            "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil"
        ),
        timeout: float = 60.0,
        policy: RetryPolicy | None = None,
        spacer: RequestSpacer | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ):
        self._enabled = enabled
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._policy = policy or RetryPolicy()
        self._spacer = spacer or RequestSpacer(1.0)
        self._transport = transport
        self._sleep = sleep

    def products(self) -> tuple[str, ...]:
        return (PRODUCT,)

    async def fetch(
        self,
        product: str,
        window: TimeWindow,
        bbox: BBox,
        *,
        previous: Mapping[str, Any] | None = None,
    ) -> ProviderResult:
        if product != PRODUCT:
            raise ValueError(f"produto INPE desconhecido: {product!r}")
        if not self._enabled:
            return ProviderResult(
                product=product,
                status="disabled",
                error_code="disabled_by_configuration",
                provenance={"reason": "INPE_QUEIMADAS_ENABLED=false"},
            )
        known = {
            f["name"]: f.get("etag")
            for f in ((previous or {}).get("files") or [])
            if f.get("etag") and f.get("status") in (200, 304)
        }
        provenance: dict[str, Any] = {"endpoint": self._base_url, "files": []}
        detections: list[NormalizedDetection] = []
        rejected = 0
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
                transport=self._transport,
            ) as client:
                for name, current_day in file_names(window):
                    file_info: dict[str, Any] = {"name": name}
                    provenance["files"].append(file_info)
                    headers = {"If-None-Match": known[name]} if name in known else None
                    response = await get_with_retries(
                        client,
                        f"{self._base_url}/{name}",
                        headers=headers,
                        policy=self._policy,
                        spacer=self._spacer,
                        sleep=self._sleep,
                    )
                    file_info["status"] = response.status_code
                    if response.status_code == 304:
                        file_info["etag"] = known[name]  # same version as last ok run
                        continue
                    if response.status_code == 404 and current_day:
                        continue  # today's file is created during the day
                    if response.status_code != 200:
                        return self._unavailable(f"http_{response.status_code}", provenance)
                    file_info.update(
                        etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"),
                        bytes=len(response.content),
                        sha256=hashlib.sha256(response.content).hexdigest(),
                    )
                    parsed = self._parse(response.content, bbox, file_info)
                    if parsed is None:
                        return self._unavailable("invalid_csv", provenance)
                    detections.extend(parsed[0])
                    rejected += parsed[1]
        except ProviderHttpError as exc:
            return self._unavailable(exc.code, provenance)
        return ProviderResult(
            product=product,
            status="ok",
            detections=tuple(detections),
            rejected=rejected,
            provenance=provenance,
        )

    @staticmethod
    def _parse(
        payload: bytes, bbox: BBox, file_info: dict[str, Any]
    ) -> tuple[list[NormalizedDetection], int] | None:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None
        reader = csv.DictReader(io.StringIO(text))
        if not set(reader.fieldnames or []) >= REQUIRED_COLUMNS:
            return None
        detections, rejected, rows, outside = [], 0, 0, 0
        try:
            for row in reader:
                rows += 1
                if None in row or any(v is None for v in row.values()):
                    rejected += 1
                    continue
                try:
                    latitude = _coordinate(row, "lat")
                    longitude = _coordinate(row, "lon")
                except RowError:
                    rejected += 1
                    continue
                if not _inside(bbox, latitude, longitude):
                    outside += 1
                    continue
                try:
                    detections.append(parse_row(row, latitude, longitude))
                except RowError:
                    rejected += 1
        except csv.Error:
            return None
        file_info.update(rows_in_file=rows, rows_outside_bbox=outside)
        return detections, rejected

    @staticmethod
    def _unavailable(code: str, provenance: dict) -> ProviderResult:
        return ProviderResult(
            product=PRODUCT, status="unavailable", error_code=code, provenance=provenance
        )
