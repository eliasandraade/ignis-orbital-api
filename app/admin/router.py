"""Admin cockpit: observability, sources, runs, permissions, settings, API spec.

Every figure is computed from the database or from this process at request
time. Nothing here is a target, an estimate or a placeholder: what cannot be
observed (CPU, memory, traffic, worker process) is reported as unavailable.
"""

import os
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import list_logs
from app.config import get_settings
from app.core.enums import UserRole
from app.core.pagination import Page
from app.core.permissions import ROLE_DESCRIPTIONS, ROLE_LABELS, endpoint_matrix
from app.database import get_db
from app.dependencies import ROLE_LEVELS, require_role
from app.orbital import queries
from app.orbital.model import IngestionRun
from app.orbital.schemas import IngestionRunRead

router = APIRouter(prefix="/api/v1/admin", tags=["administração: painel"])
_ADMIN = Depends(require_role(UserRole.ADMIN))
_DENIED = {401: {"description": "Sem autenticação"}, 403: {"description": "Somente administrador"}}
PROCESS_STARTED_AT = datetime.now(UTC)
_SCHEDULE_INTERVAL = timedelta(minutes=15)


def _stale_after() -> timedelta:
    return timedelta(minutes=get_settings().orbital_stale_after_minutes)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ORGAO)),
) -> dict:
    """Contagens institucionais (órgão e administrador)."""
    from app.incidents.model import Incident
    from app.missions.model import Mission
    from app.protected_areas.model import ProtectedArea
    from app.reports.model import PublicReport
    from app.teams.model import FieldTeam
    from app.users.model import User

    async def count(model, *where) -> int:
        return await db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    return {
        "total_incidents": await count(Incident),
        "total_reports": await count(PublicReport),
        "total_protected_areas": await count(ProtectedArea),
        "total_active_users": await count(User, User.is_active.is_(True)),
        "total_teams": await count(FieldTeam),
        "total_missions": await count(Mission),
    }


async def _database(db: AsyncSession) -> dict:
    started = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        versions = (
            await db.execute(
                text("SELECT current_setting('server_version'), postgis_lib_version()")
            )
        ).one()
        return {
            "status": "connected",
            "latency_ms": latency_ms,
            "measured_at": datetime.now(UTC),
            "postgres_version": versions[0],
            "postgis_version": versions[1],
        }
    except Exception:  # never echo driver details
        return {"status": "unreachable", "latency_ms": None, "measured_at": datetime.now(UTC)}


async def _worker_evidence(db: AsyncSession, now: datetime) -> dict:
    last = (
        await db.execute(
            select(IngestionRun.started_at, IngestionRun.finished_at, IngestionRun.status)
            .where(IngestionRun.trigger == "schedule")
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
    ).one_or_none()
    day = await db.scalar(
        select(func.count())
        .select_from(IngestionRun)
        .where(
            IngestionRun.trigger == "schedule", IngestionRun.started_at >= now - timedelta(days=1)
        )
    )
    if last is None:
        state = "no_evidence"
    elif now - last.started_at <= 2 * _SCHEDULE_INTERVAL + timedelta(minutes=5):
        state = "recent_runs"
    else:
        state = "no_recent_runs"
    return {
        "state": state,
        "last_scheduled_run_at": last.started_at if last else None,
        "last_scheduled_status": last.status if last else None,
        "scheduled_runs_last_24h": day or 0,
        "note": (
            "O IGNIS não monitora o processo do worker: este estado vem apenas das "
            "execuções agendadas registradas em ingestion_runs."
        ),
    }


@router.get("/overview", responses=_DENIED)
async def overview(db: AsyncSession = Depends(get_db), current_user=_ADMIN) -> dict:
    """Cockpit: estado observado agora e histórico registrado no banco."""
    from app.users.model import User

    settings = get_settings()
    now = datetime.now(UTC)
    database = await _database(db)
    detections = (
        await db.execute(
            text(
                "SELECT count(*) AS total,"
                " count(*) FILTER (WHERE observed_at >= now() - interval '24 hours') AS day,"
                " count(DISTINCT jurisdiction_id) FILTER"
                "   (WHERE observed_at >= now() - interval '7 days') AS munis_week,"
                " max(ingested_at) AS last_ingested FROM orbital_detections"
            )
        )
    ).one()
    municipalities = await db.scalar(
        text("SELECT count(*) FROM jurisdictions WHERE level = 'municipality'")
    )
    users = (
        await db.execute(
            select(User.role, User.is_active, func.count()).group_by(User.role, User.is_active)
        )
    ).all()
    pending_password = await db.scalar(
        select(func.count()).select_from(User).where(User.must_change_password.is_(True))
    )
    history = (
        await db.execute(
            text(
                "SELECT to_char(started_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,"
                " count(*) FILTER (WHERE status IN ('ok', 'disabled')) AS ok,"
                " count(*) FILTER (WHERE status IN ('unavailable', 'error', 'partial')) AS failed,"
                " count(*) FILTER (WHERE status = 'running') AS running"
                " FROM ingestion_runs WHERE started_at >= now() - interval '30 days'"
                " GROUP BY 1 ORDER BY 1"
            )
        )
    ).all()
    failures_week = await db.scalar(
        select(func.count())
        .select_from(IngestionRun)
        .where(
            IngestionRun.status.in_(("unavailable", "error", "partial")),
            IngestionRun.started_at >= now - timedelta(days=7),
        )
    )
    recent_runs = (
        await db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(8))
    ).all()
    recent_audit = await list_logs(db, page=1, size=8)
    by_role: dict[str, dict[str, int]] = {r.value: {"active": 0, "inactive": 0} for r in UserRole}
    for role, active, n in users:
        by_role.setdefault(role, {"active": 0, "inactive": 0})[
            "active" if active else "inactive"
        ] += n
    return {
        "generated_at": now,
        "api": {
            "status": "ok",
            "version": settings.app_version,
            "environment": settings.app_env,
            "process_started_at": PROCESS_STARTED_AT,
            "process_pid": os.getpid(),
            "note": "Instante deste processo da API; com várias réplicas, cada uma tem o seu.",
        },
        "database": database,
        "worker": await _worker_evidence(db, now),
        "data": {
            "detections_total": detections.total,
            "detections_last_24h": detections.day,
            "municipalities_monitored": municipalities or 0,
            "municipalities_with_detections_7d": detections.munis_week,
            "last_ingested_at": detections.last_ingested,
        },
        "ingestion": {
            "failures_last_7d": failures_week or 0,
            "history_30d": [
                {"day": h.day, "ok": h.ok, "failed": h.failed, "running": h.running}
                for h in history
            ],
            "recent_runs": [IngestionRunRead.model_validate(r) for r in recent_runs],
        },
        "sources": await queries.source_statuses(db, _stale_after()),
        "users": {
            "active": sum(v["active"] for v in by_role.values()),
            "inactive": sum(v["inactive"] for v in by_role.values()),
            "must_change_password": pending_password or 0,
            "by_role": by_role,
        },
        "recent_audit": recent_audit.items,
        "unavailable_metrics": [
            "CPU, memória e tráfego: sem instrumentação de infraestrutura nesta versão",
            "Latência e taxa de erro de requisições: não coletadas",
            "Disponibilidade (uptime) histórica: não coletada",
        ],
    }


@router.get("/sources", responses=_DENIED)
async def sources(db: AsyncSession = Depends(get_db), current_user=_ADMIN) -> dict:
    """Fontes de dados: configuração (sem segredos), estado e última execução por produto."""
    settings = get_settings()
    statuses = await queries.source_statuses(db, _stale_after())
    # Latest run per (source, product).
    ranked = select(
        IngestionRun.id,
        func.row_number()
        .over(
            partition_by=(IngestionRun.source, IngestionRun.product),
            order_by=IngestionRun.started_at.desc(),
        )
        .label("position"),
    ).subquery()
    latest = {
        (r.source, r.product): r
        for r in (
            await db.scalars(
                select(IngestionRun)
                .join(ranked, ranked.c.id == IngestionRun.id)
                .where(ranked.c.position == 1)
            )
        ).all()
    }
    configuration = {
        "NASA_FIRMS": {
            "configured": bool(settings.nasa_firms_map_key),
            "detail": "Chave da API configurada"
            if settings.nasa_firms_map_key
            else "Sem NASA_FIRMS_MAP_KEY: execuções ficam 'disabled', sem requisições",
            "homologated": False,
            "homologation_note": "Integração não homologada com chave real (pendência H-27).",
        },
        "INPE_QUEIMADAS": {
            "configured": settings.inpe_queimadas_enabled,
            "detail": "Arquivos diários de dados abertos (sem chave)"
            if settings.inpe_queimadas_enabled
            else "Desligada por INPE_QUEIMADAS_ENABLED=false",
            "homologated": True,
            "homologation_note": "Validada com dados públicos reais (Sprint 1.2).",
        },
    }
    result = []
    for status in statuses:
        products = []
        for product in status.products:
            run = latest.get((status.source, product.product))
            products.append(
                {
                    **product.model_dump(),
                    "last_run": IngestionRunRead.model_validate(run) if run else None,
                }
            )
        result.append(
            {
                **status.model_dump(exclude={"products"}),
                "configuration": configuration[status.source],
                "products": products,
            }
        )
    dataset = await queries.current_dataset(db)
    return {
        "sources": result,
        "reference_data": [
            {
                "source": "IBGE",
                "product": "Malha Municipal Digital",
                "state": "loaded" if dataset else "missing",
                "dataset": dataset.model_dump() if dataset else None,
                "detail": "Importada no pre-deploy (seed.jurisdictions), conferida por SHA-256",
            }
        ],
    }


@router.get("/ingestion-runs", responses=_DENIED)
async def ingestion_runs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    source: Literal["NASA_FIRMS", "INPE_QUEIMADAS"] | None = Query(None),
    product: str | None = Query(None, max_length=64),
    status: Literal["running", "ok", "partial", "unavailable", "disabled", "error"] | None = Query(
        None
    ),
    trigger: Literal["schedule", "manual"] | None = Query(None),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    current_user=_ADMIN,
) -> Page[IngestionRunRead]:
    """Execuções registradas em ingestion_runs (não o estado do processo do worker)."""
    conditions = []
    if source:
        conditions.append(IngestionRun.source == source)
    if product:
        conditions.append(IngestionRun.product == product)
    if status:
        conditions.append(IngestionRun.status == status)
    if trigger:
        conditions.append(IngestionRun.trigger == trigger)
    if date_from:
        conditions.append(IngestionRun.started_at >= date_from)
    if date_to:
        conditions.append(IngestionRun.started_at < date_to)
    total = await db.scalar(select(func.count()).select_from(IngestionRun).where(*conditions))
    rows = (
        await db.scalars(
            select(IngestionRun)
            .where(*conditions)
            .order_by(IngestionRun.started_at.desc(), IngestionRun.id)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return Page.create(
        items=[IngestionRunRead.model_validate(r) for r in rows],
        total=total or 0,
        page=page,
        size=size,
    )


@router.get("/ingestion-runs/{run_id}", response_model=IngestionRunRead, responses=_DENIED)
async def ingestion_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user=_ADMIN):
    """Detalhe de uma execução: contadores, erro sanitizado e proveniência."""
    from app.core.exceptions import NotFoundException

    run = await db.get(IngestionRun, run_id)
    if run is None:
        raise NotFoundException("Execução")
    return IngestionRunRead.model_validate(run)


@router.get("/permissions", responses=_DENIED)
async def permissions(request: Request, current_user=_ADMIN) -> dict:
    """Matriz RBAC lida das dependências de cada rota montada (RBAC estático)."""
    roles = sorted(ROLE_LEVELS, key=ROLE_LEVELS.get)
    return {
        "model": "hierarchical_static",
        "note": (
            "Papéis fixos e hierárquicos: cada papel herda o acesso dos anteriores. "
            "A permissão é verificada no backend em cada endpoint; a interface só reflete."
        ),
        "roles": [
            {
                "role": r.value,
                "label": ROLE_LABELS[r],
                "level": ROLE_LEVELS[r],
                "description": ROLE_DESCRIPTIONS[r],
            }
            for r in roles
        ],
        "endpoints": [asdict(rule) for rule in endpoint_matrix(request.app)],
    }


@router.get("/settings", responses=_DENIED)
async def settings_view(db: AsyncSession = Depends(get_db), current_user=_ADMIN) -> dict:
    """Configuração efetiva sem segredos. Tudo é gerido pelo ambiente (variáveis)."""
    from app.core.passwords import MIN_PASSWORD_LENGTH

    s = get_settings()
    dataset = await queries.current_dataset(db)
    build = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("IGNIS_BUILD_SHA")
    return {
        "managed_by": "ambiente (variáveis do serviço). Esta tela não altera configurações.",
        "application": {
            "name": "IGNIS Orbital",
            "vendor": "Andrade Systems",
            "version": s.app_version,
            "environment": s.app_env,
            "build_commit": build[:12] if build else None,
            "api_docs_public": s.docs_public,
        },
        "data_sources": {
            "nasa_firms_configured": bool(s.nasa_firms_map_key),
            "inpe_queimadas_enabled": s.inpe_queimadas_enabled,
            "stale_after_minutes": s.orbital_stale_after_minutes,
            "ingest_window_hours": s.ingest_window_hours,
            "ingest_round_timeout_seconds": s.ingest_round_timeout_seconds,
            "reference_dataset": dataset.model_dump() if dataset else None,
        },
        "security": {
            "jwt_expiration_minutes": s.jwt_access_token_expire_minutes,
            "password_min_length": MIN_PASSWORD_LENGTH,
            "rate_limit_enabled": s.rate_limit_enabled,
            "rate_limit_scope": "por processo (memória)",
            "trust_proxy_headers": s.trust_proxy_headers,
            "client_ip_header": s.client_ip_header,
            "cors_origins": s.cors_origins,
        },
    }


@router.get("/openapi.json", responses=_DENIED)
async def protected_openapi(request: Request, current_user=_ADMIN) -> dict:
    """A especificação completa da API, para administradores — também quando
    /docs e /openapi.json públicos estão desligados (staging/produção)."""
    return request.app.openapi()
