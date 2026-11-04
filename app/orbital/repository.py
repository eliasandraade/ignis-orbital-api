"""The only code path that writes ingestion runs and orbital detections.

Every function works inside the caller's transaction and never commits: a
batch's rows and its counters become visible together or not at all.

Liveness of a running execution is a lease, not a clock: the process that
owns a run holds a session-level advisory lock keyed by the run id on its
own connection (acquire_lease). PostgreSQL releases that lock when the
owner's connection ends for any reason (normal exit, crash, SIGKILL, lost
network), so recover_abandoned_runs only closes runs whose owner is gone,
however long a live one has been working.
"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.orbital.contracts import (
    FINAL_STATUSES,
    DetectionSource,
    NormalizedDetection,
    RunStatus,
    TimeWindow,
    Trigger,
)
from app.orbital.model import IngestionRun

MAX_BATCH = 5000
ERROR_MESSAGE_MAX = 500


class RunAlreadyActiveError(RuntimeError):
    """Another execution of the same (source, product) is still running."""


class RunNotActiveError(RuntimeError):
    """The run already finished; its counters are frozen."""


@dataclass(frozen=True, slots=True)
class BatchResult:
    fetched: int
    valid: int
    rejected: int
    out_of_scope: int
    inserted: int
    duplicate: int


_LEASE_KEY = "hashtextextended('ignis:ingestion_run:' || CAST(CAST(:run_id AS uuid) AS text), 0)"


async def acquire_lease(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Take the run's session-level lock on this session's connection.

    The connection must stay open (and not be returned to a pool) for as long
    as the run is in progress; it survives commits, so no transaction has to
    stay open while the owner talks to external providers.
    """
    acquired = await session.scalar(
        text(f"SELECT pg_try_advisory_lock({_LEASE_KEY})"), {"run_id": run_id}
    )
    if not acquired:  # a fresh random id is never locked; refuse to share it
        raise RunAlreadyActiveError(f"lease de {run_id} já pertence a outro processo")


async def release_lease(session: AsyncSession, run_id: uuid.UUID) -> None:
    await session.execute(text(f"SELECT pg_advisory_unlock({_LEASE_KEY})"), {"run_id": run_id})


async def recover_abandoned_runs(
    session: AsyncSession, source: DetectionSource, product: str
) -> list[uuid.UUID]:
    """Close the running executions of (source, product) whose owner is gone.

    A run is abandoned only when its lease can be taken, i.e. no live
    connection holds it. A run that is still working is never touched,
    whatever its age. Recovered runs become 'error'/'abandoned' with their
    counters intact: what they committed stays stored and counted.
    """
    running = (
        await session.scalars(
            select(IngestionRun.id)
            .where(
                IngestionRun.source == DetectionSource(source).value,
                IngestionRun.product == product,
                IngestionRun.status == RunStatus.RUNNING.value,
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    recovered = []
    for run_id in running:
        owner_gone = await session.scalar(
            text(f"SELECT pg_try_advisory_xact_lock({_LEASE_KEY})"), {"run_id": run_id}
        )
        if owner_gone:
            recovered.append(run_id)
    if recovered:
        await session.execute(
            update(IngestionRun)
            .where(IngestionRun.id.in_(recovered))
            .values(
                status=RunStatus.ERROR.value,
                finished_at=datetime.now(UTC),
                error_code="abandoned",
                error_message=(
                    "Execução interrompida sem finalizar: o processo dono encerrou "
                    "ou perdeu a conexão com o banco."
                ),
            )
        )
    return recovered


async def start_run(
    session: AsyncSession,
    source: DetectionSource,
    product: str,
    *,
    trigger: Trigger,
    window: TimeWindow | None = None,
    triggered_by_user_id: uuid.UUID | None = None,
    params: dict | None = None,
    run_id: uuid.UUID | None = None,
) -> IngestionRun:
    """Register a running execution, or raise RunAlreadyActiveError.

    The partial unique index uq_ingestion_runs_one_running is the guard, so
    the check holds across processes and replicas, not only in this one.
    Pass the run_id whose lease the caller already holds (acquire_lease).
    """
    run = IngestionRun(
        id=run_id or uuid.uuid4(),
        source=DetectionSource(source).value,
        product=product,
        trigger=trigger,
        triggered_by_user_id=triggered_by_user_id,
        status=RunStatus.RUNNING.value,
        window_start=window.start if window else None,
        window_end=window.end if window else None,
        params=params or {},
    )
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError as exc:
        if "uq_ingestion_runs_one_running" in str(exc.orig):
            raise RunAlreadyActiveError(f"{source}/{product} já está em execução") from exc
        raise
    await session.refresh(run)
    return run


_INSERT_BATCH = text(
    """
WITH input AS (
    SELECT *
    FROM unnest(
        CAST(:dedup_keys AS uuid[]),
        CAST(:products AS text[]),
        CAST(:satellites AS text[]),
        CAST(:instruments AS text[]),
        CAST(:observed_at AS timestamptz[]),
        CAST(:longitudes AS float8[]),
        CAST(:latitudes AS float8[]),
        CAST(:confidences AS text[]),
        CAST(:confidence_pcts AS int[]),
        CAST(:frps AS float8[]),
        CAST(:brightness AS float8[]),
        CAST(:brightness_channels AS text[]),
        CAST(:daynights AS text[]),
        CAST(:provider_ids AS text[]),
        CAST(:raws AS text[])
    ) AS t(dedup_key, product, satellite, instrument, observed_at, longitude, latitude,
           confidence, confidence_pct, frp_mw, brightness_k, brightness_channel, daynight,
           provider_record_id, raw)
),
located AS (
    SELECT i.*, ST_SetSRID(ST_MakePoint(i.longitude, i.latitude), 4326) AS location
    FROM input AS i
),
scoped AS (
    SELECT l.*, m.id AS jid
    FROM located AS l
    LEFT JOIN LATERAL (
        -- A point on a shared border belongs to the lowest IBGE code: deterministic.
        SELECT j.id
        FROM jurisdictions AS j
        WHERE j.level = 'municipality' AND ST_Covers(j.geom, l.location)
        ORDER BY j.ibge_code
        LIMIT 1
    ) AS m ON true
),
inserted AS (
    INSERT INTO orbital_detections (
        dedup_key, source, product, satellite, instrument, observed_at, location,
        confidence, confidence_pct, frp_mw, brightness_k, brightness_channel, daynight,
        provider_record_id, jurisdiction_id, ingestion_run_id, raw
    )
    SELECT dedup_key, CAST(:source AS text), product, satellite, instrument, observed_at,
           location, confidence, confidence_pct, frp_mw, brightness_k, brightness_channel,
           daynight, provider_record_id, jid, CAST(:run_id AS uuid), CAST(raw AS jsonb)
    FROM scoped
    WHERE jid IS NOT NULL
    -- One global lock order: overlapping batches written concurrently in
    -- different orders would otherwise deadlock on the unique index.
    ORDER BY dedup_key
    ON CONFLICT (dedup_key) DO NOTHING
    RETURNING 1
)
SELECT
    (SELECT count(*) FROM scoped WHERE jid IS NULL) AS out_of_scope,
    (SELECT count(*) FROM inserted) AS inserted
"""
)


async def _lock_running(session: AsyncSession, run_id: uuid.UUID) -> IngestionRun:
    run = await session.scalar(
        select(IngestionRun)
        .where(IngestionRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise LookupError(f"ingestion_run {run_id} não existe")
    if run.status != RunStatus.RUNNING:
        raise RunNotActiveError(f"ingestion_run {run_id} já terminou ({run.status})")
    return run


async def persist_batch(
    session: AsyncSession,
    run_id: uuid.UUID,
    detections: Sequence[NormalizedDetection],
    *,
    rejected: int = 0,
) -> BatchResult:
    """Store one batch and add exactly what happened to the run's counters.

    inserted comes from RETURNING, so it counts rows this statement wrote;
    duplicate is everything valid and in scope that already existed (in the
    table, or earlier in the same batch). Concurrent writers are safe:
    ON CONFLICT resolves races on dedup_key, rows are inserted in dedup_key
    order (no lock-order deadlock between overlapping batches), and the run
    row lock serialises counter updates. Commit after each batch: locks held
    across several batches of one transaction can still conflict.
    """
    if rejected < 0:
        raise ValueError("rejected não pode ser negativo")
    if len(detections) > MAX_BATCH:
        raise ValueError(f"lote acima de {MAX_BATCH} detecções; divida a chamada")
    run = await _lock_running(session, run_id)
    for detection in detections:
        if detection.source != run.source:
            raise ValueError(f"detecção de {detection.source} em execução de {run.source}")

    out_of_scope = inserted = 0
    if detections:
        row = (
            await session.execute(
                _INSERT_BATCH,
                {
                    "source": run.source,
                    "run_id": run.id,
                    "dedup_keys": [d.dedup_key for d in detections],
                    "products": [d.product for d in detections],
                    "satellites": [d.satellite for d in detections],
                    "instruments": [d.instrument for d in detections],
                    "observed_at": [d.observed_at.astimezone(UTC) for d in detections],
                    "longitudes": [d.longitude for d in detections],
                    "latitudes": [d.latitude for d in detections],
                    "confidences": [d.confidence for d in detections],
                    "confidence_pcts": [d.confidence_pct for d in detections],
                    "frps": [d.frp_mw for d in detections],
                    "brightness": [d.brightness_k for d in detections],
                    "brightness_channels": [d.brightness_channel for d in detections],
                    "daynights": [d.daynight for d in detections],
                    "provider_ids": [d.provider_record_id for d in detections],
                    "raws": [json.dumps(dict(d.raw), default=str) for d in detections],
                },
            )
        ).one()
        out_of_scope, inserted = int(row.out_of_scope), int(row.inserted)

    valid = len(detections)
    result = BatchResult(
        fetched=valid + rejected,
        valid=valid,
        rejected=rejected,
        out_of_scope=out_of_scope,
        inserted=inserted,
        duplicate=valid - out_of_scope - inserted,
    )
    await session.execute(
        update(IngestionRun)
        .where(IngestionRun.id == run.id)
        .values(
            records_fetched=IngestionRun.records_fetched + result.fetched,
            records_valid=IngestionRun.records_valid + result.valid,
            records_rejected=IngestionRun.records_rejected + result.rejected,
            records_out_of_scope=IngestionRun.records_out_of_scope + result.out_of_scope,
            records_inserted=IngestionRun.records_inserted + result.inserted,
            records_duplicate=IngestionRun.records_duplicate + result.duplicate,
        )
    )
    return result


async def finish_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: RunStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    params: dict | None = None,
) -> IngestionRun:
    """Freeze a run. `params` is merged into the run's params (provenance)."""
    if status not in FINAL_STATUSES:
        raise ValueError(f"status final inválido: {status!r}")
    run = await _lock_running(session, run_id)
    run.status = RunStatus(status).value
    run.finished_at = datetime.now(UTC)
    run.error_code = error_code
    run.error_message = error_message[:ERROR_MESSAGE_MAX] if error_message else None
    if params:
        run.params = {**(run.params or {}), **params}
    await session.flush()
    return run


async def last_successful_params(
    session: AsyncSession, source: DetectionSource, product: str
) -> dict | None:
    """Provenance of the latest 'ok' run, for conditional requests (ETag)."""
    return await session.scalar(
        select(IngestionRun.params)
        .where(
            IngestionRun.source == DetectionSource(source).value,
            IngestionRun.product == product,
            IngestionRun.status == RunStatus.OK.value,
        )
        .order_by(IngestionRun.finished_at.desc())
        .limit(1)
    )
