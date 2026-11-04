import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import get_settings
from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.rate_limit import rate_limit
from app.database import engine as app_engine
from app.database import get_db
from app.dependencies import require_role
from app.integrations.nasa_firms.schemas import OrbitalAlertListResponse
from app.integrations.nasa_firms.service import list_alerts
from app.orbital.contracts import DetectionProvider
from app.orbital.ingestion import IngestionRound
from app.orbital.model import IngestionRun
from app.orbital.providers import SOURCES, providers_from_settings
from app.orbital.schemas import IngestAccepted, IngestionRunRead, IngestRequest, StartedRun

logger = logging.getLogger("ignis.ingestion")
router = APIRouter(prefix="/api/v1/orbital-alerts", tags=["orbital-alerts"])


def get_ingestion_engine() -> AsyncEngine:
    return app_engine


def get_ingestion_providers() -> list[DetectionProvider]:
    return providers_from_settings(get_settings())


@router.get(
    "",
    dependencies=[Depends(rate_limit("orbital-alerts", limit=60, window_seconds=60))],
)
async def get_orbital_alerts() -> OrbitalAlertListResponse:
    """List orbital heat-spot alerts (satellite thermal anomalies, not confirmed fires).

    source_status:
    - `live` / `cached`: NASA FIRMS data fetched now / earlier (see `fetched_at`).
    - `demo`: fictitious items, only when ORBITAL_ALERTS_DEMO_MODE=true.
    - `disabled_missing_api_key`: NASA_FIRMS_MAP_KEY absent — empty list.
    - `unavailable`: NASA FIRMS failed — empty list.

    This read endpoint never starts an ingestion run; reading from
    orbital_detections replaces it in Sprint 1.3.
    """
    return await list_alerts()


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
