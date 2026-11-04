"""One ingestion round: fetch → validate → normalize → locate → persist → finish.

A round owns one dedicated database connection for its whole life. On it,
each run holds its lease (app.orbital.repository.acquire_lease), and short
transactions create runs, persist batches and finish runs. No transaction is
open while a provider talks to NASA or INPE: the connection is idle, holding
only the leases, which PostgreSQL drops by itself if this process dies.

Status of each (source, product) run:
- ok / disabled / unavailable: what the provider reported;
- partial: some batches were committed, then a timeout or failure stopped it;
- error: nothing was committed and the round failed on our side
  (error_code "timeout", "interrupted", "internal_error", ...);
- skipped_active: not a run — another live process is running that product.
"""

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.orbital import repository
from app.orbital.contracts import (
    CEARA_BBOX,
    BBox,
    DetectionProvider,
    ProviderResult,
    RunStatus,
    TimeWindow,
    Trigger,
)

logger = logging.getLogger("ignis.ingestion")

DEFAULT_WINDOW = timedelta(hours=26)  # one day plus overlap with the previous round
_PROVIDER_STATUS = {
    "ok": RunStatus.OK,
    "unavailable": RunStatus.UNAVAILABLE,
    "disabled": RunStatus.DISABLED,
}


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


@dataclass(slots=True)
class ProductRun:
    provider: DetectionProvider
    product: str
    run_id: uuid.UUID | None = None
    status: str = "pending"
    error_code: str | None = None
    previous: dict[str, Any] | None = None
    batches_committed: int = 0
    counters: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(
            ("fetched", "valid", "rejected", "out_of_scope", "inserted", "duplicate"), 0
        )
    )

    @property
    def source(self) -> str:
        return self.provider.source.value

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "product": self.product,
            "run_id": str(self.run_id) if self.run_id else None,
            "status": self.status,
            "error_code": self.error_code,
            **{f"records_{k}": v for k, v in self.counters.items()},
        }


@dataclass(frozen=True, slots=True)
class RoundResult:
    runs: tuple[ProductRun, ...]

    @property
    def exit_code(self) -> int:
        """0: every product ok/disabled/skipped; 2: a provider failed or a run is
        partial; 1: our side failed (timeout, interruption, internal error)."""
        statuses = {r.status for r in self.runs}
        if statuses & {RunStatus.ERROR.value}:
            return 1
        if statuses & {RunStatus.UNAVAILABLE.value, RunStatus.PARTIAL.value}:
            return 2
        return 0

    def summary(self) -> list[dict[str, Any]]:
        return [r.summary() for r in self.runs]


class IngestionRound:
    def __init__(
        self,
        engine: AsyncEngine,
        providers: Sequence[DetectionProvider],
        *,
        trigger: Trigger,
        window: TimeWindow | None = None,
        bbox: BBox = CEARA_BBOX,
        triggered_by_user_id: uuid.UUID | None = None,
        batch_size: int = 1000,
        product_timeout: float = 300.0,
    ):
        self.id = uuid.uuid4()
        self._engine = engine
        self._trigger = trigger
        self._window = window or TimeWindow.last(DEFAULT_WINDOW)
        self._bbox = bbox
        self._user_id = triggered_by_user_id
        self._batch_size = batch_size
        self._product_timeout = product_timeout
        self.runs = [ProductRun(p, product) for p in providers for product in p.products()]
        self._conn: AsyncConnection | None = None
        self._session: AsyncSession | None = None

    # -- lifecycle --------------------------------------------------------------

    async def start(self) -> list[ProductRun]:
        """Create one run per product (or mark it skipped_active)."""
        self._conn = await self._engine.connect()
        self._session = AsyncSession(bind=self._conn, expire_on_commit=False)
        try:
            for run in self.runs:
                await self._start_run(run)
        except BaseException:
            await self.abort("internal_error")
            raise
        return self.runs

    async def execute(self) -> RoundResult:
        """Process every started run, then release the connection.

        Runs not reached because the round was cancelled are finished as
        'error'/'interrupted', so nothing stays 'running' behind a live lease.
        """
        try:
            for run in self.runs:
                if run.status == RunStatus.RUNNING.value:
                    await self._process(run)
        except BaseException:
            await self._finish_unprocessed("interrupted")
            raise
        finally:
            await self._close()
        return RoundResult(tuple(self.runs))

    async def run(self) -> RoundResult:
        await self.start()
        return await self.execute()

    async def abort(self, code: str) -> None:
        await self._finish_unprocessed(code)
        await self._close()

    # -- steps ------------------------------------------------------------------

    async def _start_run(self, run: ProductRun) -> None:
        session = self._session
        source = run.provider.source
        async with session.begin():
            recovered = await repository.recover_abandoned_runs(session, source, run.product)
            for run_id in recovered:
                logger.warning(
                    "execução abandonada recuperada: %s/%s %s", source, run.product, run_id
                )
            last = await repository.last_successful_params(session, source, run.product)
            run.previous = (last or {}).get("provenance")
            run_id = uuid.uuid4()
            await repository.acquire_lease(session, run_id)
            try:
                await repository.start_run(
                    session,
                    source,
                    run.product,
                    trigger=self._trigger,
                    window=self._window,
                    triggered_by_user_id=self._user_id,
                    params={
                        "round_id": str(self.id),
                        "worker": worker_id(),
                        "bbox": list(self._bbox),
                    },
                    run_id=run_id,
                )
            except repository.RunAlreadyActiveError:
                await repository.release_lease(session, run_id)
                run.status = "skipped_active"
                return
        run.run_id = run_id
        run.status = RunStatus.RUNNING.value

    async def _process(self, run: ProductRun) -> None:
        try:
            async with asyncio.timeout(self._product_timeout):
                # No transaction is open here: only the lease is held.
                result = await run.provider.fetch(
                    run.product, self._window, self._bbox, previous=run.previous
                )
                await self._persist(run, result)
            await self._finish(
                run,
                _PROVIDER_STATUS[result.status],
                error_code=result.error_code,
                params={"provenance": dict(result.provenance)},
            )
        except TimeoutError:
            await self._fail(run, "timeout")
        except asyncio.CancelledError:
            await self._fail(run, "interrupted")
            raise
        except Exception as exc:  # our bug or the database: never the provider's
            logger.exception("falha interna na ingestão %s/%s", run.source, run.product)
            await self._fail(run, "internal_error", message=type(exc).__name__)

    async def _persist(self, run: ProductRun, result: ProviderResult) -> None:
        if result.status != "ok":
            return
        session = self._session
        detections = result.detections
        chunks = [
            detections[i : i + self._batch_size]
            for i in range(0, len(detections), self._batch_size)
        ] or [()]
        for index, chunk in enumerate(chunks):
            async with session.begin():
                batch = await repository.persist_batch(
                    session, run.run_id, chunk, rejected=result.rejected if index == 0 else 0
                )
            run.batches_committed += 1
            for key in run.counters:
                run.counters[key] += getattr(batch, key)

    async def _finish(
        self,
        run: ProductRun,
        status: RunStatus,
        *,
        error_code: str | None = None,
        message: str | None = None,
        params: dict | None = None,
    ) -> None:
        session = self._session
        try:
            async with session.begin():
                await repository.finish_run(
                    session,
                    run.run_id,
                    status,
                    error_code=error_code,
                    error_message=message,
                    params=params,
                )
                await repository.release_lease(session, run.run_id)
            run.status, run.error_code = status.value, error_code
        except Exception:
            # Connection lost or broken: the lease dies with it and the next
            # round recovers this run as abandoned.
            logger.exception("não foi possível finalizar %s", run.run_id)
            run.status, run.error_code = RunStatus.ERROR.value, error_code or "finish_failed"

    async def _fail(self, run: ProductRun, code: str, *, message: str | None = None) -> None:
        if self._session.in_transaction():
            await asyncio.shield(self._session.rollback())
        status = RunStatus.PARTIAL if run.batches_committed else RunStatus.ERROR
        await asyncio.shield(self._finish(run, status, error_code=code, message=message))

    async def _finish_unprocessed(self, code: str) -> None:
        if self._session is None:
            return
        for run in self.runs:
            if run.status == RunStatus.RUNNING.value and run.run_id is not None:
                await asyncio.shield(self._fail(run, code))

    async def _close(self) -> None:
        if self._session is not None:
            await asyncio.shield(self._session.close())
            self._session = None
        if self._conn is not None:
            await asyncio.shield(self._conn.close())  # drops any lease still held
            self._conn = None
