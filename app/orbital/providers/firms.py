"""NASA FIRMS area API (CSV) → NormalizedDetection.

Endpoint: {base}/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{DATE}
returns detections from DATE through DATE + DAY_RANGE - 1 (DAY_RANGE 1..5).

Field semantics follow the FIRMS attribute table for MODIS and VIIRS 375 m:
- acq_date + acq_time: overpass time in UTC (acq_time HHMM);
- VIIRS: confidence is a class (low/nominal/high); bright_ti4 is the I-4
  channel brightness temperature (K);
- MODIS: confidence is a 0-100 % estimate (no published class boundaries,
  so it is stored as confidence_pct and never mapped to a class);
  brightness is channels 21/22 (K);
- frp: pixel-integrated fire radiative power in MW (both sensors);
- satellite: N = Suomi NPP, N20 = NOAA-20, N21 = NOAA-21; MODIS A = Aqua,
  T = Terra.
Every other column (scan, track, version, bright_ti5/bright_t31, ...) is kept
verbatim in `raw`.
"""

import asyncio
import csv
import hashlib
import io
import math
from collections.abc import Mapping
from dataclasses import dataclass
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

MAX_DAY_RANGE = 5


@dataclass(frozen=True, slots=True)
class FirmsProduct:
    instrument: str
    satellites: Mapping[str, str]  # FIRMS code → canonical satellite name


VIIRS_COLUMNS = frozenset(
    {
        "latitude",
        "longitude",
        "bright_ti4",
        "acq_date",
        "acq_time",
        "satellite",
        "confidence",
        "version",
        "frp",
        "daynight",
    }
)
MODIS_COLUMNS = frozenset(
    {
        "latitude",
        "longitude",
        "brightness",
        "acq_date",
        "acq_time",
        "satellite",
        "confidence",
        "version",
        "frp",
        "daynight",
    }
)

PRODUCTS: dict[str, FirmsProduct] = {
    "VIIRS_SNPP_NRT": FirmsProduct("VIIRS", {"N": "Suomi NPP"}),
    "VIIRS_NOAA20_NRT": FirmsProduct("VIIRS", {"N20": "NOAA-20"}),
    "VIIRS_NOAA21_NRT": FirmsProduct("VIIRS", {"N21": "NOAA-21"}),
    "MODIS_NRT": FirmsProduct(
        "MODIS", {"T": "Terra", "A": "Aqua", "TERRA": "Terra", "AQUA": "Aqua"}
    ),
}

_VIIRS_CONFIDENCE = {
    "l": "low",
    "low": "low",
    "n": "nominal",
    "nominal": "nominal",
    "h": "high",
    "high": "high",
}


class RowError(ValueError):
    """One CSV row violates the documented format (counted as rejected)."""


def _number(row: Mapping[str, str], column: str, *, required: bool = True) -> float | None:
    raw = (row.get(column) or "").strip()
    if not raw:
        if required:
            raise RowError(f"{column} vazio")
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise RowError(f"{column} não numérico") from exc
    if not math.isfinite(value):
        raise RowError(f"{column} não finito")
    return value


def _observed_at(row: Mapping[str, str]) -> datetime:
    acq_time = (row.get("acq_time") or "").strip()
    if not acq_time.isdigit() or len(acq_time) > 4:
        raise RowError("acq_time inválido")
    acq_time = acq_time.zfill(4)
    try:
        return datetime.strptime(
            f"{(row.get('acq_date') or '').strip()} {acq_time}", "%Y-%m-%d %H%M"
        ).replace(tzinfo=UTC)
    except ValueError as exc:
        raise RowError("acq_date/acq_time inválidos") from exc


def _sensor_fields(instrument: str, row: Mapping[str, str]) -> dict[str, Any]:
    """Confidence and brightness exactly as the sensor reports them."""
    if instrument == "VIIRS":
        confidence = _VIIRS_CONFIDENCE.get((row.get("confidence") or "").strip().lower())
        if confidence is None:
            raise RowError("confidence VIIRS fora de low/nominal/high")
        brightness = _number(row, "bright_ti4", required=False)
        return {
            "confidence": confidence,
            "brightness_k": brightness,
            "brightness_channel": "VIIRS_I4" if brightness is not None else None,
        }
    pct = _number(row, "confidence")
    if pct is None or not pct.is_integer() or not 0 <= pct <= 100:
        raise RowError("confidence MODIS fora de 0..100")
    brightness = _number(row, "brightness", required=False)
    return {
        "confidence_pct": int(pct),
        "brightness_k": brightness,
        "brightness_channel": "MODIS_21_22" if brightness is not None else None,
    }


def parse_row(product_id: str, row: Mapping[str, str]) -> NormalizedDetection:
    product = PRODUCTS[product_id]
    code = (row.get("satellite") or "").strip()
    satellite = product.satellites.get(code) or product.satellites.get(code.upper())
    if satellite is None:
        raise RowError(f"satélite {code!r} não pertence a {product_id}")
    instrument = (row.get("instrument") or product.instrument).strip().upper()
    if instrument != product.instrument:
        raise RowError(f"instrumento {instrument!r} não pertence a {product_id}")

    sensor = _sensor_fields(product.instrument, row)

    daynight = (row.get("daynight") or "").strip().upper() or None
    try:
        return NormalizedDetection(
            source=DetectionSource.NASA_FIRMS,
            product=product_id,
            satellite=satellite,
            instrument=product.instrument,
            observed_at=_observed_at(row),
            latitude=_number(row, "latitude"),
            longitude=_number(row, "longitude"),
            frp_mw=_number(row, "frp", required=False),
            daynight=daynight,
            **sensor,
            raw=dict(row),
        )
    except InvalidDetectionError as exc:
        raise RowError(str(exc)) from exc


def day_range(window: TimeWindow) -> tuple[str, int]:
    """FIRMS DATE and DAY_RANGE covering every UTC day touched by the window."""
    first = window.start.astimezone(UTC).date()
    last = window.end.astimezone(UTC).date()
    days = (last - first).days + 1
    if days > MAX_DAY_RANGE:
        first = last - timedelta(days=MAX_DAY_RANGE - 1)
        days = MAX_DAY_RANGE
    return first.isoformat(), days


class FirmsProvider:
    source = DetectionSource.NASA_FIRMS

    def __init__(
        self,
        map_key: str,
        *,
        base_url: str = "https://firms.modaps.eosdis.nasa.gov/api",
        timeout: float = 30.0,
        policy: RetryPolicy | None = None,
        spacer: RequestSpacer | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        products: tuple[str, ...] = tuple(PRODUCTS),
    ):
        unknown = set(products) - set(PRODUCTS)
        if unknown:
            raise ValueError(f"produtos FIRMS desconhecidos: {sorted(unknown)}")
        self._key = map_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._policy = policy or RetryPolicy()
        self._spacer = spacer or RequestSpacer(1.0)
        self._transport = transport
        self._sleep = sleep
        self._products = products

    def products(self) -> tuple[str, ...]:
        return self._products

    async def fetch(
        self,
        product: str,
        window: TimeWindow,
        bbox: BBox,
        *,
        previous: Mapping[str, Any] | None = None,
    ) -> ProviderResult:
        del previous  # the area API has no conditional requests (no ETag)
        if not self._key:
            return ProviderResult(
                product=product,
                status="disabled",
                error_code="missing_api_key",
                provenance={"reason": "NASA_FIRMS_MAP_KEY não configurada"},
            )
        date, days = day_range(window)
        area = ",".join(f"{v:g}" for v in bbox)
        provenance: dict[str, Any] = {
            "endpoint": "api/area/csv",
            "source_product": product,
            "area": area,
            "day_range": days,
            "date": date,
        }
        url = f"{self._base_url}/area/csv/{self._key}/{product}/{area}/{days}/{date}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
                transport=self._transport,
            ) as client:
                response = await get_with_retries(
                    client, url, policy=self._policy, spacer=self._spacer, sleep=self._sleep
                )
        except ProviderHttpError as exc:
            return self._unavailable(product, exc.code, provenance)

        provenance["http_status"] = response.status_code
        body = response.text
        if response.status_code != 200:
            rejected_key = "invalid map_key" in body.lower()
            return self._unavailable(
                product,
                "auth_rejected" if rejected_key else f"http_{response.status_code}",
                provenance,
            )
        provenance["bytes"] = len(response.content)
        provenance["sha256"] = hashlib.sha256(response.content).hexdigest()
        return self._parse(product, body, provenance)

    def _parse(self, product: str, body: str, provenance: dict) -> ProviderResult:
        reader = csv.DictReader(io.StringIO(body))
        expected = VIIRS_COLUMNS if PRODUCTS[product].instrument == "VIIRS" else MODIS_COLUMNS
        columns = set(reader.fieldnames or [])
        if not expected <= columns:
            # FIRMS answers some errors as plain text; never read them as "0 fires".
            provenance["missing_columns"] = sorted(expected - columns)[:20]
            return self._unavailable(product, "invalid_csv", provenance)
        detections, rejected, rows = [], 0, 0
        try:
            for row in reader:
                rows += 1
                if None in row or any(v is None for v in row.values()):
                    rejected += 1  # wrong number of fields
                    continue
                try:
                    detections.append(parse_row(product, row))
                except RowError:
                    rejected += 1
        except csv.Error:
            return self._unavailable(product, "invalid_csv", provenance)
        provenance["rows_received"] = rows
        return ProviderResult(
            product=product,
            status="ok",
            detections=tuple(detections),
            rejected=rejected,
            provenance=provenance,
        )

    @staticmethod
    def _unavailable(product: str, code: str, provenance: dict) -> ProviderResult:
        return ProviderResult(
            product=product, status="unavailable", error_code=code, provenance=provenance
        )
