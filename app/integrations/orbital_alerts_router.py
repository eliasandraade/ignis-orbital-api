import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import get_settings
from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.rate_limit import rate_limit
from app.database import engine as app_engine
from app.database import get_db
from app.dependencies import require_role
from app.orbital import queries
from app.orbital.contracts import DetectionProvider
from app.orbital.ingestion import IngestionRound
from app.orbital.model import IngestionRun
from app.orbital.providers import SOURCES, providers_from_settings
from app.orbital.read_schemas import DetectionDetail, DetectionPage, DetectionStats, SourceStatus
from app.orbital.schemas import IngestAccepted, IngestionRunRead, IngestRequest, StartedRun

logger = logging.getLogger("ignis.ingestion")
router = APIRouter(prefix="/api/v1/orbital-alerts", tags=["orbital-alerts"])


def get_ingestion_engine() -> AsyncEngine:
    return app_engine


def get_ingestion_providers() -> list[DetectionProvider]:
    return providers_from_settings(get_settings())


def _filters(
    observed_from: datetime | None,
    observed_to: datetime | None,
    source: str | None,
    satellite: str | None,
    jurisdiction: str | None,
    bbox: str | None,
) -> queries.Filters:
    try:
        return queries.build_filters(
            observed_from=observed_from,
            observed_to=observed_to,
            source=source,
            satellite=satellite,
            jurisdiction=jurisdiction,
            bbox=bbox,
        )
    except queries.FilterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _stale_after() -> timedelta:
    return timedelta(minutes=get_settings().orbital_stale_after_minutes)


FromQ = Query(
    None, alias="from", description="Início da observação (ISO 8601); padrão: to - 7 dias"
)
ToQ = Query(None, alias="to", description="Fim da observação (ISO 8601, exclusivo); padrão: agora")
SourceQ = Query(None, description="NASA_FIRMS ou INPE_QUEIMADAS")
SatelliteQ = Query(None, max_length=64)
JurisdictionQ = Query(None, description="Código IBGE de 7 dígitos do município")
BBoxQ = Query(None, description="oeste,sul,leste,norte (graus, SRID 4326)")
_BAD_FILTER = {422: {"description": "Filtro inválido (janela, fonte, município ou bbox)"}}
_PUBLIC_LIMIT = [Depends(rate_limit("orbital-alerts", limit=60, window_seconds=60))]


@router.get("", dependencies=_PUBLIC_LIMIT, responses=_BAD_FILTER)
async def get_orbital_alerts(
    observed_from: datetime | None = FromQ,
    observed_to: datetime | None = ToQ,
    source: str | None = SourceQ,
    satellite: str | None = SatelliteQ,
    jurisdiction: str | None = JurisdictionQ,
    bbox: str | None = BBoxQ,
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(500, ge=1, le=queries.MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
) -> DetectionPage:
    """Persisted heat spots (satellite thermal anomalies, never confirmed fires).

    Reads only PostgreSQL/PostGIS: it never calls NASA or INPE. `sources`
    reports each provider's ingestion state separately from the observation
    times of the detections (`observed_at`) and from when IGNIS stored them
    (`ingested_at`). An empty `items` with a `live` source means "no detection
    in the window"; with `disabled`, `unavailable` or `never_ingested` it
    means "no data to judge".
    """
    f = _filters(observed_from, observed_to, source, satellite, jurisdiction, bbox)
    return await queries.list_detections(db, f, page=page, size=size, stale_after=_stale_after())


@router.get("/sources", dependencies=_PUBLIC_LIMIT)
async def get_sources(db: AsyncSession = Depends(get_db)) -> list[SourceStatus]:
    """Ingestion state of NASA FIRMS and INPE, product by product."""
    return await queries.source_statuses(db, _stale_after())


@router.get("/stats", dependencies=_PUBLIC_LIMIT, responses=_BAD_FILTER)
async def get_stats(
    observed_from: datetime | None = FromQ,
    observed_to: datetime | None = ToQ,
    source: str | None = SourceQ,
    satellite: str | None = SatelliteQ,
    jurisdiction: str | None = JurisdictionQ,
    bbox: str | None = BBoxQ,
    db: AsyncSession = Depends(get_db),
) -> DetectionStats:
    """Counts computed from the stored detections, with the same filters."""
    f = _filters(observed_from, observed_to, source, satellite, jurisdiction, bbox)
    return await queries.detection_stats(db, f, stale_after=_stale_after())


async def _execute(ingestion: IngestionRound) -> None:
    try:
        result = await ingestion.execute()
        logger.info("ingestão manual %s concluída: %s", ingestion.id, result.summary())
    except Exception:
        logger.exception("ingestão manual %s falhou", ingestion.id)


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingest(
    background: BackgroundTasks,
    body: IngestRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
    engine: AsyncEngine = Depends(get_ingestion_engine),
    providers: list[DetectionProvider] = Depends(get_ingestion_providers),
) -> IngestAccepted:
    """Start one ingestion round (admin only) and return its real runs.

    The runs exist in `ingestion_runs` with status `running` when this
    returns (202); processing continues in the background. The outcome is
    known only from GET /ingestion-runs/{run_id}: this response never
    reports data as fetched or stored.
    """
    selected = tuple((body.sources if body and body.sources else None) or SOURCES)
    wanted = {"firms": "NASA_FIRMS", "inpe": "INPE_QUEIMADAS"}
    providers = [p for p in providers if p.source.value in {wanted[s] for s in selected}]
    ingestion = IngestionRound(
        engine,
        providers,
        trigger="manual",
        triggered_by_user_id=current_user.id,
        product_timeout=get_settings().ingest_product_timeout_seconds,
    )
    runs = await ingestion.start()
    started = [
        StartedRun(
            run_id=r.run_id,
            source=r.source,
            product=r.product,
            status="running" if r.run_id else "skipped_active",
        )
        for r in runs
    ]
    try:
        await log_action(
            db,
            "orbital_ingest.requested",
            "IngestionRound",
            str(ingestion.id),
            actor_name=current_user.name,
            actor_id=current_user.id,
            metadata={
                "sources": list(selected),
                "runs": [r.model_dump(mode="json") for r in started],
            },
        )
        await db.commit()
    except BaseException:
        # Never leave runs 'running' behind a live connection nobody will use.
        await ingestion.abort("internal_error")
        raise
    if any(r.run_id for r in runs):
        background.add_task(_execute, ingestion)
        return IngestAccepted(
            status="accepted",
            round_id=ingestion.id,
            message=(
                "Execução iniciada em segundo plano. Nenhum resultado é afirmado aqui: "
                "consulte GET /api/v1/orbital-alerts/ingestion-runs/{run_id}."
            ),
            runs=started,
        )
    await ingestion.abort("nothing_started")
    return IngestAccepted(
        status="nothing_started",
        round_id=ingestion.id,
        message="Nenhuma execução iniciada: todos os produtos já estão em execução.",
        runs=started,
    )


@router.get("/ingestion-runs", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def list_ingestion_runs(
    limit: int = 20, db: AsyncSession = Depends(get_db)
) -> list[IngestionRunRead]:
    rows = await db.scalars(
        select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(min(max(limit, 1), 100))
    )
    return [IngestionRunRead.model_validate(r) for r in rows]


@router.get(
    "/ingestion-runs/{run_id}",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    responses={404: {"description": "Execução não encontrada"}},
)
async def get_ingestion_run(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> IngestionRunRead:
    run = await db.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return IngestionRunRead.model_validate(run)


# Last: "/{detection_id}" would otherwise shadow the literal paths above.
@router.get(
    "/{detection_id}",
    dependencies=_PUBLIC_LIMIT,
    responses={404: {"description": "Detecção não encontrada"}},
)
async def get_detection(
    detection_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> DetectionDetail:
    """One stored detection, with the provider's original row (`raw`)."""
    detection = await queries.get_detection(db, detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Detecção não encontrada")
    return detection
