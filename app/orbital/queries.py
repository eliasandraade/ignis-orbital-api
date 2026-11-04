"""Read-only queries over orbital_detections, ingestion_runs and jurisdictions.

Every query is bounded: a time window (at most MAX_WINDOW_DAYS), a page size
(at most MAX_PAGE_SIZE) and optional filters validated before they reach SQL.
Each list or count is one statement (no per-row queries), using the indexes
on (source, observed_at), (jurisdiction_id, observed_at), observed_at and
the GiST index on location.
"""

import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.orbital.read_schemas import (
    AppliedFilters,
    CountBucket,
    DatasetRef,
    DayBucket,
    Detection,
    DetectionDetail,
    DetectionPage,
    DetectionStats,
    JurisdictionRef,
    MunicipalityCount,
    MunicipalityList,
    MunicipalitySummary,
    ProductStatus,
    SourceStatus,
)

MAX_WINDOW_DAYS = 92
DEFAULT_WINDOW = timedelta(days=7)
MAX_PAGE_SIZE = 5000
SOURCES = ("NASA_FIRMS", "INPE_QUEIMADAS")
SOURCE_LABELS = {"NASA_FIRMS": "NASA FIRMS", "INPE_QUEIMADAS": "INPE Programa Queimadas"}
EXPECTED_PRODUCTS = {
    "NASA_FIRMS": ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"),
    "INPE_QUEIMADAS": ("FOCOS_DIARIO_BR",),
}
_SATELLITE = re.compile(r"^[A-Za-z0-9 _.-]{1,64}$")
_IBGE_CODE = re.compile(r"^\d{7}$")
# Generous envelope around Ceará: a bbox must intersect it and stay small.
_MAX_BBOX_SPAN_DEG = 20.0


class FilterError(ValueError):
    """A filter value is invalid; the message is safe to return to clients."""


@dataclass(frozen=True, slots=True)
class Filters:
    observed_from: datetime
    observed_to: datetime
    source: str | None = None
    satellite: str | None = None
    jurisdiction: str | None = None
    bbox: tuple[float, float, float, float] | None = None

    def applied(self) -> AppliedFilters:
        return AppliedFilters(
            observed_from=self.observed_from,
            observed_to=self.observed_to,
            source=self.source,
            satellite=self.satellite,
            jurisdiction=self.jurisdiction,
            bbox=list(self.bbox) if self.bbox else None,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None or raw == "":
        return None
    try:
        west, south, east, north = (float(v) for v in raw.split(","))
    except ValueError as exc:
        raise FilterError("bbox deve ser 'oeste,sul,leste,norte' em graus decimais") from exc
    values = (west, south, east, north)
    if not all(math.isfinite(v) for v in values):
        raise FilterError("bbox com valor não finito")
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise FilterError("bbox fora de ordem ou de faixa")
    if east - west > _MAX_BBOX_SPAN_DEG or north - south > _MAX_BBOX_SPAN_DEG:
        raise FilterError(f"bbox maior que {_MAX_BBOX_SPAN_DEG:g}° em algum eixo")
    return values


def build_filters(
    *,
    observed_from: datetime | None,
    observed_to: datetime | None,
    source: str | None,
    satellite: str | None,
    jurisdiction: str | None,
    bbox: str | None,
    now: datetime | None = None,
) -> Filters:
    end = _aware(observed_to) if observed_to else (now or datetime.now(UTC))
    start = _aware(observed_from) if observed_from else end - DEFAULT_WINDOW
    if start >= end:
        raise FilterError("'from' deve ser anterior a 'to'")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise FilterError(f"janela máxima de {MAX_WINDOW_DAYS} dias")
    if source is not None and source not in SOURCES:
        raise FilterError(f"source deve ser um de {', '.join(SOURCES)}")
    if satellite is not None and not _SATELLITE.match(satellite):
        raise FilterError("satellite inválido")
    if jurisdiction is not None and not _IBGE_CODE.match(jurisdiction):
        raise FilterError("jurisdiction deve ser o código IBGE de 7 dígitos do município")
    return Filters(start, end, source, satellite, jurisdiction, parse_bbox(bbox))


def _where(f: Filters) -> tuple[str, dict]:
    clauses = ["d.observed_at >= :from_", "d.observed_at < :to_"]
    params: dict = {"from_": f.observed_from, "to_": f.observed_to}
    if f.source:
        clauses.append("d.source = :source")
        params["source"] = f.source
    if f.satellite:
        clauses.append("d.satellite = :satellite")
        params["satellite"] = f.satellite
    if f.jurisdiction:
        clauses.append("j.ibge_code = :ibge")
        params["ibge"] = f.jurisdiction
    if f.bbox:
        clauses.append("d.location && ST_MakeEnvelope(:w, :s, :e, :n, 4326)")
        params.update(dict(zip(("w", "s", "e", "n"), f.bbox, strict=True)))
    return " AND ".join(clauses), params


_DETECTION_COLUMNS = """
    d.id, d.source, d.product, d.satellite, d.instrument, d.observed_at, d.ingested_at,
    ST_Y(d.location) AS lat, ST_X(d.location) AS lng, j.ibge_code, j.name AS jurisdiction_name,
    d.confidence, d.confidence_pct, d.frp_mw, d.brightness_k, d.brightness_channel,
    d.daynight, d.provider_record_id, d.ingestion_run_id
"""


def _detection(row) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "product": row.product,
        "satellite": row.satellite,
        "instrument": row.instrument,
        "observed_at": row.observed_at,
        "ingested_at": row.ingested_at,
        "lat": row.lat,
        "lng": row.lng,
        "jurisdiction": JurisdictionRef(ibge_code=row.ibge_code, name=row.jurisdiction_name),
        "confidence": row.confidence,
        "confidence_pct": row.confidence_pct,
        "frp_mw": float(row.frp_mw) if row.frp_mw is not None else None,
        "brightness_k": float(row.brightness_k) if row.brightness_k is not None else None,
        "brightness_channel": row.brightness_channel,
        "daynight": row.daynight,
        "provider_record_id": row.provider_record_id,
        "ingestion_run_id": row.ingestion_run_id,
    }


async def list_detections(
    session: AsyncSession, f: Filters, *, page: int, size: int, stale_after: timedelta
) -> DetectionPage:
    where, params = _where(f)
    total = await session.scalar(
        text(
            "SELECT count(*) FROM orbital_detections d"
            " JOIN jurisdictions j ON j.id = d.jurisdiction_id WHERE " + where
        ),
        params,
    )
    rows = (
        await session.execute(
            text(
                "SELECT " + _DETECTION_COLUMNS + " FROM orbital_detections d"
                " JOIN jurisdictions j ON j.id = d.jurisdiction_id WHERE "
                + where
                + " ORDER BY d.observed_at DESC, d.id LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": size, "offset": (page - 1) * size},
        )
    ).all()
    return DetectionPage(
        items=[Detection(**_detection(r)) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=max(1, math.ceil(total / size)),
        truncated=total > page * size,
        filters=f.applied(),
        sources=await source_statuses(session, stale_after),
    )


async def get_detection(session: AsyncSession, detection_id: uuid.UUID) -> DetectionDetail | None:
    row = (
        await session.execute(
            text(
                "SELECT " + _DETECTION_COLUMNS + ", d.raw FROM orbital_detections d"
                " JOIN jurisdictions j ON j.id = d.jurisdiction_id WHERE d.id = :id"
            ),
            {"id": detection_id},
        )
    ).one_or_none()
    if row is None:
        return None
    return DetectionDetail(**_detection(row), raw=row.raw)


async def detection_stats(
    session: AsyncSession, f: Filters, *, stale_after: timedelta, top: int = 10
) -> DetectionStats:
    where, params = _where(f)
    base = (
        "FROM orbital_detections d JOIN jurisdictions j ON j.id = d.jurisdiction_id WHERE " + where
    )
    summary = (
        await session.execute(
            text(
                "SELECT count(*) AS total, count(DISTINCT d.jurisdiction_id) AS munis,"
                " min(d.observed_at) AS first, max(d.observed_at) AS last,"
                " max(d.ingested_at) AS ingested " + base
            ),
            params,
        )
    ).one()

    async def buckets(expr: str, order: str = "count DESC, key") -> list:
        return (
            await session.execute(
                text(f"SELECT {expr} AS key, count(*) AS count {base} GROUP BY 1 ORDER BY {order}"),
                params,
            )
        ).all()

    by_day = await buckets("to_char(d.observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')", order="key")
    top_rows = (
        await session.execute(
            text(
                "SELECT j.ibge_code, j.name, count(*) AS count "
                + base
                + " GROUP BY j.ibge_code, j.name ORDER BY count DESC, j.name LIMIT :top"
            ),
            {**params, "top": top},
        )
    ).all()
    return DetectionStats(
        filters=f.applied(),
        total=summary.total,
        municipalities_with_detections=summary.munis,
        by_source=[CountBucket(key=r.key, count=r.count) for r in await buckets("d.source")],
        by_satellite=[CountBucket(key=r.key, count=r.count) for r in await buckets("d.satellite")],
        by_day=[DayBucket(day=r.key, count=r.count) for r in by_day],
        top_municipalities=[
            MunicipalityCount(ibge_code=r.ibge_code, name=r.name, count=r.count) for r in top_rows
        ],
        first_observed_at=summary.first,
        last_observed_at=summary.last,
        last_ingested_at=summary.ingested,
        sources=await source_statuses(session, stale_after),
    )


# --- source status ----------------------------------------------------------------------

_SOURCE_MESSAGES = {
    "live": "Última ingestão concluída dentro do prazo esperado.",
    "stale": "Dados desatualizados: a última ingestão bem-sucedida é antiga.",
    "degraded": "Parte dos produtos falhou na última tentativa; os demais estão atualizados.",
    "unavailable": "A última tentativa de ingestão falhou: a fonte está indisponível.",
    "disabled": "Fonte desabilitada nesta instalação (não configurada).",
    "never_ingested": "Nenhuma ingestão desta fonte foi executada ainda.",
}


def _product_state(last_status: str | None, last_success: datetime | None, now, stale_after):
    if last_status is None:
        return "never_ingested"
    if last_status == "disabled":
        return "disabled"
    if last_status in ("unavailable", "error", "partial"):
        return "unavailable"
    if last_success is not None and now - last_success <= stale_after:
        return "live"
    return "stale"


def _source_state(states: list[str]) -> str:
    active = [s for s in states if s != "disabled"]
    if not active:
        return "disabled"
    if all(s == "never_ingested" for s in active):
        return "never_ingested"
    failing = any(s == "unavailable" for s in active)
    if any(s == "live" for s in active):
        return "degraded" if failing else "live"
    if failing:
        return "unavailable"
    return "stale"


async def source_statuses(
    session: AsyncSession, stale_after: timedelta, now: datetime | None = None
) -> list[SourceStatus]:
    now = now or datetime.now(UTC)
    rows = (
        await session.execute(
            text(
                """
WITH last_finished AS (
    SELECT DISTINCT ON (source, product)
           source, product, status, error_code, finished_at,
           params->'provenance'->>'origin' AS origin
    FROM ingestion_runs
    WHERE status <> 'running'
    ORDER BY source, product, finished_at DESC
),
last_ok AS (
    SELECT DISTINCT ON (source, product)
           source, product, finished_at, params->'provenance'->>'origin' AS origin
    FROM ingestion_runs
    WHERE status = 'ok'
    ORDER BY source, product, finished_at DESC
),
running AS (
    SELECT source, product, true AS running FROM ingestion_runs WHERE status = 'running'
)
SELECT f.source, f.product, f.status, f.error_code, f.finished_at,
       o.finished_at AS last_ok, coalesce(o.origin, f.origin) AS origin,
       coalesce(r.running, false) AS running
FROM last_finished f
LEFT JOIN last_ok o USING (source, product)
LEFT JOIN running r USING (source, product)
"""
            )
        )
    ).all()
    latest = dict(
        (
            await session.execute(
                text(
                    "SELECT s.source, (SELECT max(observed_at) FROM orbital_detections d"
                    " WHERE d.source = s.source) FROM unnest(CAST(:sources AS text[])) AS s(source)"
                ),
                {"sources": list(SOURCES)},
            )
        ).all()
    )
    by_key = {(r.source, r.product): r for r in rows}
    return [
        _source_status(source, by_key, latest.get(source), now, stale_after) for source in SOURCES
    ]


def _product_status(product: str, r, now: datetime, stale_after: timedelta) -> ProductStatus:
    if r is None:
        return ProductStatus(
            product=product,
            state="never_ingested",
            last_attempt_at=None,
            last_attempt_status=None,
            last_error_code=None,
            last_success_at=None,
            running=False,
            origin=None,
        )
    return ProductStatus(
        product=product,
        state=_product_state(r.status, r.last_ok, now, stale_after),
        last_attempt_at=r.finished_at,
        last_attempt_status=r.status,
        last_error_code=r.error_code,
        last_success_at=r.last_ok,
        running=bool(r.running),
        origin=_origin(r.origin),
    )


def _source_status(source, by_key, latest_observation, now, stale_after) -> SourceStatus:
    extra = sorted(
        product
        for (s, product) in by_key
        if s == source and product not in EXPECTED_PRODUCTS[source]
    )
    products = [
        _product_status(product, by_key.get((source, product)), now, stale_after)
        for product in [*EXPECTED_PRODUCTS[source], *extra]
    ]
    state = _source_state([p.state for p in products])
    successes = [p.last_success_at for p in products if p.last_success_at]
    origins = {p.origin for p in products if p.origin}
    fixture = "fixture" in origins
    message = _SOURCE_MESSAGES[state]
    if fixture:
        message += " Amostra histórica pública (fixture), não dados atuais."
    origin = None
    if origins:
        origin = "fixture" if fixture else "live"
    return SourceStatus(
        source=source,
        label=SOURCE_LABELS[source],
        state=state,
        message=message,
        last_success_at=max(successes) if successes else None,
        latest_observation_at=latest_observation,
        stale_after_minutes=int(stale_after.total_seconds() // 60),
        origin=origin,
        products=products,
    )


def _origin(value: str | None):
    if value == "fixture":
        return "fixture"
    return "live" if value else None


# --- jurisdictions ----------------------------------------------------------------------


async def current_dataset(session: AsyncSession) -> DatasetRef | None:
    row = (
        await session.execute(
            text(
                "SELECT r.source, r.product, r.version, r.reference_date, r.content_sha256"
                " FROM reference_datasets r WHERE r.id = ("
                "  SELECT dataset_id FROM jurisdictions WHERE level = 'state' LIMIT 1)"
            )
        )
    ).one_or_none()
    if row is None:
        return None
    return DatasetRef(
        source=row.source,
        product=row.product,
        version=row.version,
        reference_date=row.reference_date.isoformat(),
        content_sha256=row.content_sha256,
    )


async def list_municipalities(session: AsyncSession, f: Filters) -> MunicipalityList | None:
    dataset = await current_dataset(session)
    if dataset is None:
        return None
    where, params = _where(f)
    rows = (
        await session.execute(
            text(
                "WITH counts AS (SELECT d.jurisdiction_id, count(*) AS n FROM orbital_detections d"
                " JOIN jurisdictions j ON j.id = d.jurisdiction_id WHERE "
                + where
                + " GROUP BY d.jurisdiction_id)"
                " SELECT j.ibge_code, j.name, j.official_area_km2, coalesce(c.n, 0) AS detections"
                " FROM jurisdictions j LEFT JOIN counts c ON c.jurisdiction_id = j.id"
                " WHERE j.level = 'municipality' ORDER BY j.name"
            ),
            params,
        )
    ).all()
    return MunicipalityList(
        items=[
            MunicipalitySummary(
                ibge_code=r.ibge_code,
                name=r.name,
                official_area_km2=float(r.official_area_km2),
                detections=r.detections,
            )
            for r in rows
        ],
        total=len(rows),
        dataset=dataset,
        filters=f.applied(),
    )


async def jurisdictions_geojson(session: AsyncSession, level: str, tolerance: float) -> str | None:
    """FeatureCollection (SRID 4326) built by PostGIS, returned as JSON text.

    tolerance > 0 simplifies each polygon for display only
    (ST_SimplifyPreserveTopology); the stored official geometry never changes.
    """
    return await session.scalar(
        text(
            """
SELECT json_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(json_agg(json_build_object(
        'type', 'Feature',
        'id', j.ibge_code,
        'properties', json_build_object(
            'ibge_code', j.ibge_code, 'name', j.name, 'level', j.level,
            'official_area_km2', j.official_area_km2),
        'geometry', ST_AsGeoJSON(
            CASE WHEN CAST(:tol AS float8) > 0
                 THEN ST_SimplifyPreserveTopology(j.geom, CAST(:tol AS float8)) ELSE j.geom END,
            6)::json
    ) ORDER BY j.ibge_code), '[]'::json),
    'dataset', (SELECT json_build_object('source', r.source, 'product', r.product,
                                         'version', r.version,
                                         'reference_date', r.reference_date,
                                         'content_sha256', r.content_sha256)
                FROM reference_datasets r WHERE r.id = min(j.dataset_id::text)::uuid),
    'simplification_tolerance_deg', CAST(:tol AS float8)
)::text
FROM jurisdictions j
WHERE j.level = :level
HAVING count(*) > 0
"""
        ),
        {"level": level, "tol": tolerance},
    )
