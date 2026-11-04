"""Sprint 1.2 — ingestion rounds against a real PostGIS (tests/postgis.py).

Providers talk to tests/orbital_support.RecordingTransport (real public
fixtures); the database, leases, recovery and concurrency are real.
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.orbital import repository
from app.orbital.contracts import DetectionSource, ProviderResult
from app.orbital.ingestion import IngestionRound
from app.orbital.model import IngestionRun
from app.orbital.providers._http import RequestSpacer, RetryPolicy
from app.orbital.providers.firms import FirmsProvider
from app.orbital.providers.inpe import InpeProvider
from tests import postgis
from tests.orbital_support import (
    FAKE_KEY,
    FIXTURE_COUNTS,
    INPE_ETAG,
    WINDOW,
    RecordingTransport,
    fixture_bytes,
)

ROOT = postgis.ROOT


async def no_sleep(_):
    return None


def providers(transport, key=FAKE_KEY, firms_products=None):
    firms = FirmsProvider(
        key,
        transport=transport,
        policy=RetryPolicy(attempts=2),
        spacer=RequestSpacer(0),
        sleep=no_sleep,
        **({"products": firms_products} if firms_products else {}),
    )
    inpe = InpeProvider(
        transport=transport, policy=RetryPolicy(attempts=2), spacer=RequestSpacer(0), sleep=no_sleep
    )
    return [firms, inpe]


def make_round(engine, provs, **kwargs):
    return IngestionRound(engine, provs, trigger="schedule", window=WINDOW, **kwargs)


async def runs_by_product(engine):
    async with AsyncSession(engine) as session:
        rows = (await session.scalars(select(IngestionRun).order_by(IngestionRun.started_at))).all()
    return {r.product: r for r in rows}


async def scalar(engine, sql, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar()


class StubProvider:
    """A provider whose fetch runs a test-supplied coroutine."""

    source = DetectionSource.NASA_FIRMS

    def __init__(self, fetch, products=("VIIRS_NOAA20_NRT",)):
        self._fetch = fetch
        self._products = products

    def products(self):
        return self._products

    async def fetch(self, product, window, bbox, *, previous=None):
        return await self._fetch(product)


# --- successful rounds ------------------------------------------------------------


async def test_full_round_stores_real_detections_inside_ceara(clean_orbital):
    engine = clean_orbital
    transport = RecordingTransport()
    result = await make_round(engine, providers(transport)).run()

    assert result.exit_code == 0
    assert {r.status for r in result.runs} == {"ok"}
    runs = await runs_by_product(engine)
    assert set(runs) == set(FIXTURE_COUNTS)
    async with engine.connect() as conn:
        per_run = dict(
            (
                await conn.execute(
                    text(
                        "SELECT ingestion_run_id, count(*) FROM orbital_detections"
                        " GROUP BY ingestion_run_id"
                    )
                )
            ).all()
        )
        outside_ce = await conn.scalar(
            text(
                "SELECT count(*) FROM orbital_detections d JOIN jurisdictions j"
                " ON j.id = d.jurisdiction_id WHERE j.level <> 'municipality'"
                " OR j.state_ibge_code <> '23'"
            )
        )
        not_covered = await conn.scalar(
            text(
                "SELECT count(*) FROM orbital_detections d JOIN jurisdictions j"
                " ON j.id = d.jurisdiction_id WHERE NOT ST_Covers(j.geom, d.location)"
            )
        )
    for product, run in runs.items():
        assert run.status == "ok"
        assert run.records_valid == FIXTURE_COUNTS[product]
        assert run.records_fetched == run.records_valid + run.records_rejected
        assert run.records_valid == (
            run.records_inserted + run.records_duplicate + run.records_out_of_scope
        )
        assert per_run.get(run.id, 0) == run.records_inserted  # counters = rows written
        assert run.params["provenance"]
        assert FAKE_KEY not in json.dumps(run.params)
    # The request envelope reaches PI, RN, PB and PE: those points are counted, not stored.
    assert sum(r.records_out_of_scope for r in runs.values()) > 0
    assert outside_ce == 0
    assert not_covered == 0
    assert runs["FOCOS_DIARIO_BR"].params["provenance"]["files"][0]["etag"] == INPE_ETAG


async def test_detections_keep_provenance_and_utc_times(clean_orbital):
    engine = clean_orbital
    await make_round(engine, providers(RecordingTransport())).run()
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT source, product, satellite, instrument, observed_at, ingested_at,"
                    " ST_X(location) lon, ST_Y(location) lat, confidence, confidence_pct,"
                    " brightness_k, brightness_channel, frp_mw, raw"
                    " FROM orbital_detections WHERE product = 'MODIS_NRT' LIMIT 1"
                )
            )
        ).one()
        inpe = (
            await conn.execute(
                text(
                    "SELECT provider_record_id, raw->>'id' AS raw_id, frp_mw, confidence,"
                    " confidence_pct FROM orbital_detections WHERE source = 'INPE_QUEIMADAS'"
                    " LIMIT 1"
                )
            )
        ).one()
    assert (row.source, row.instrument, row.brightness_channel) == (
        "NASA_FIRMS",
        "MODIS",
        "MODIS_21_22",
    )
    assert row.satellite in {"Terra", "Aqua"}
    assert row.confidence is None
    assert 0 <= row.confidence_pct <= 100
    assert row.observed_at.utcoffset() == timedelta(0)
    assert row.ingested_at >= row.observed_at
    assert float(row.raw["latitude"]) == pytest.approx(row.lat)
    assert row.raw["acq_time"]  # original fields kept verbatim
    assert inpe.provider_record_id == inpe.raw_id
    assert (inpe.frp_mw, inpe.confidence, inpe.confidence_pct) == (None, None, None)


async def test_reprocessing_the_same_window_writes_nothing(clean_orbital):
    engine = clean_orbital
    transport = RecordingTransport()
    first = await make_round(engine, providers(transport)).run()
    total = await scalar(engine, "SELECT count(*) FROM orbital_detections")
    second = await make_round(engine, providers(transport)).run()

    assert first.exit_code == second.exit_code == 0
    assert await scalar(engine, "SELECT count(*) FROM orbital_detections") == total
    for run in second.runs:
        assert run.counters["inserted"] == 0
        if run.product != "FOCOS_DIARIO_BR":
            assert run.counters["duplicate"] == run.counters["valid"] - run.counters["out_of_scope"]
    inpe_requests = [r for r in transport.requests if "focos_diario" in r.url.path]
    assert inpe_requests[-1].headers.get("if-none-match") == INPE_ETAG  # conditional, 304


async def test_same_observation_twice_in_one_batch_is_one_row(clean_orbital):
    engine = clean_orbital
    header, *rows = fixture_bytes("VIIRS_NOAA20_NRT").decode().splitlines()
    body = "\n".join([header, *rows, *rows[:50]]) + "\n"
    transport = RecordingTransport(
        lambda r: httpx.Response(200, text=body) if "/VIIRS_NOAA20_NRT/" in r.url.path else None
    )
    result = await make_round(
        engine, providers(transport, firms_products=("VIIRS_NOAA20_NRT",))[:1]
    ).run()
    (run,) = result.runs
    counters = run.counters
    assert counters["valid"] == 277
    assert counters["duplicate"] > 0  # repeated in-scope rows, recognised in the batch
    assert counters["inserted"] + counters["duplicate"] + counters["out_of_scope"] == 277
    stored = await scalar(engine, "SELECT count(*) FROM orbital_detections")
    assert stored == counters["inserted"] <= 227


# --- provider failures ---------------------------------------------------------------


async def test_without_key_firms_runs_are_disabled_with_nothing_stored(clean_orbital):
    engine = clean_orbital
    transport = RecordingTransport()
    result = await make_round(engine, providers(transport, key="")[:1]).run()
    assert result.exit_code == 0
    assert {r.status for r in result.runs} == {"disabled"}
    assert {r.error_code for r in result.runs} == {"missing_api_key"}
    assert transport.requests == []
    assert await scalar(engine, "SELECT count(*) FROM orbital_detections") == 0
    assert await scalar(engine, "SELECT max(records_fetched) FROM ingestion_runs") == 0


async def test_unavailable_provider_fabricates_nothing(clean_orbital):
    engine = clean_orbital
    transport = RecordingTransport(lambda r: httpx.Response(503, text="maintenance"))
    result = await make_round(engine, providers(transport)).run()
    assert result.exit_code == 2
    assert {r.status for r in result.runs} == {"unavailable"}
    assert {r.error_code for r in result.runs} == {"http_503"}
    assert await scalar(engine, "SELECT count(*) FROM orbital_detections") == 0


async def test_no_transaction_is_open_while_the_provider_works(clean_orbital, geo_engine):
    engine = clean_orbital
    observed = {}

    async def fetch(product):
        async with geo_engine.connect() as probe:  # another connection looks at the owner
            observed["states"] = (
                (
                    await probe.execute(
                        text(
                            "SELECT a.state FROM pg_stat_activity a JOIN pg_locks l"
                            " ON l.pid = a.pid WHERE l.locktype = 'advisory' AND l.granted"
                        )
                    )
                )
                .scalars()
                .all()
            )
        return ProviderResult(product=product, status="ok")

    result = await make_round(engine, [StubProvider(fetch)]).run()
    assert result.runs[0].status == "ok"
    assert observed["states"] == ["idle"]  # holding only the lease, not a transaction
    assert await scalar(engine, "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'") == 0


# --- timeouts, interruption, crashes, lost connections ------------------------------


async def test_product_timeout_finishes_the_run_and_releases_the_lease(clean_orbital):
    engine = clean_orbital

    async def slow(product):
        await asyncio.sleep(30)

    result = await make_round(engine, [StubProvider(slow)], product_timeout=0.5).run()
    (run,) = result.runs
    assert (run.status, run.error_code) == ("error", "timeout")
    assert result.exit_code == 1
    stored = (await runs_by_product(engine))["VIIRS_NOAA20_NRT"]
    assert (stored.status, stored.error_code) == ("error", "timeout")
    assert await scalar(engine, "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'") == 0


async def test_cancelled_round_closes_every_run_as_interrupted(clean_orbital):
    engine = clean_orbital
    entered = asyncio.Event()

    async def hang(product):
        entered.set()
        await asyncio.Event().wait()

    ingestion = make_round(engine, [StubProvider(hang, products=("VIIRS_NOAA20_NRT", "MODIS_NRT"))])
    task = asyncio.create_task(ingestion.run())
    await asyncio.wait_for(entered.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    runs = await runs_by_product(engine)
    assert {(r.status, r.error_code) for r in runs.values()} == {("error", "interrupted")}
    assert await scalar(engine, "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'") == 0


async def test_failure_after_committed_batches_is_partial(clean_orbital, monkeypatch):
    engine = clean_orbital
    real = repository.persist_batch
    calls = {"n": 0}

    async def flaky(session, run_id, detections, *, rejected=0):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("disk full")
        return await real(session, run_id, detections, rejected=rejected)

    monkeypatch.setattr(repository, "persist_batch", flaky)
    provs = providers(RecordingTransport(), firms_products=("VIIRS_NOAA20_NRT",))[:1]
    result = await make_round(engine, provs, batch_size=100).run()
    (run,) = result.runs
    assert (run.status, run.error_code) == ("partial", "internal_error")
    stored = (await runs_by_product(engine))["VIIRS_NOAA20_NRT"]
    rows = await scalar(engine, "SELECT count(*) FROM orbital_detections")
    assert stored.records_inserted == rows  # the committed batch, and only it
    assert stored.records_valid == 100
    assert stored.error_message == "RuntimeError"


async def test_killed_process_run_is_recovered_by_the_next_round(clean_orbital, geo_database):
    engine = clean_orbital
    child = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tests" / "ingest_owner_process.py"),
            postgis.asyncpg_url(geo_database),
        ],
        cwd=ROOT,
        env={**os.environ, "APP_ENV": "test", "PYTHONPATH": str(ROOT)},
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        run_id = uuid.UUID(child.stdout.readline().strip())
        # Alive: another round must neither touch it nor start a second one.
        blocked = await make_round(engine, [StubProvider(lambda p: None)]).run()
        assert blocked.runs[0].status == "skipped_active"
        child.kill()  # SIGKILL / TerminateProcess: no cleanup code runs
        child.wait(timeout=30)
    finally:
        if child.poll() is None:
            child.kill()
        child.stdout.close()

    async def ok(product):
        return ProviderResult(product=product, status="ok")

    for _ in range(50):  # the server notices the dead connection almost at once
        async with AsyncSession(engine) as session:
            recovered = await repository.recover_abandoned_runs(
                session, DetectionSource.NASA_FIRMS, "VIIRS_NOAA20_NRT"
            )
            await session.commit()
        if recovered:
            break
        await asyncio.sleep(0.2)
    assert recovered == [run_id]
    result = await make_round(engine, [StubProvider(ok)]).run()
    assert result.runs[0].status == "ok"
    runs = await runs_by_product(engine)
    assert runs["VIIRS_NOAA20_NRT"].status == "ok"
    async with AsyncSession(engine) as session:
        abandoned = await session.get(IngestionRun, run_id)
    assert (abandoned.status, abandoned.error_code) == ("error", "abandoned")


async def test_lost_database_connection_is_recorded_not_left_running(clean_orbital, geo_engine):
    """The owner's connection is killed mid-round (network cut, failover).
    The round reconnects to record the failure; nothing stays 'running'.
    (If it cannot reconnect at all, the lease died with the connection and
    the next round recovers the run: see the killed-process test.)"""
    engine = clean_orbital

    async def cut_connection(product):
        async with geo_engine.begin() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_locks"
                    " WHERE locktype = 'advisory' AND granted"
                )
            )
        return ProviderResult(product=product, status="ok")

    result = await make_round(engine, [StubProvider(cut_connection)]).run()
    (run,) = result.runs
    assert (run.status, run.error_code) == ("error", "internal_error")
    async with AsyncSession(engine) as session:
        stored = await session.get(IngestionRun, run.run_id)
        assert (stored.status, stored.error_code) == ("error", "internal_error")
        assert stored.finished_at is not None
        assert (
            await repository.recover_abandoned_runs(
                session, DetectionSource.NASA_FIRMS, "VIIRS_NOAA20_NRT"
            )
            == []
        )
    assert await scalar(engine, "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'") == 0


# --- concurrency -------------------------------------------------------------------------


async def test_concurrent_rounds_never_run_the_same_product_twice(clean_orbital):
    engine = clean_orbital
    gate = asyncio.Event()

    async def wait_gate(product):
        await gate.wait()
        return ProviderResult(product=product, status="ok")

    products = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT")
    engines = [create_async_engine(engine.url, poolclass=NullPool) for _ in range(3)]
    try:
        rounds = [make_round(e, [StubProvider(wait_gate, products)]) for e in engines]
        started = await asyncio.gather(*(r.start() for r in rounds))
        owners = {}
        for runs in started:
            for run in runs:
                if run.run_id:
                    assert run.product not in owners
                    owners[run.product] = run.run_id
        assert set(owners) == set(products)
        assert sum(1 for runs in started for r in runs if r.status == "skipped_active") == 6
        gate.set()
        results = await asyncio.gather(*(r.execute() for r in rounds))
    finally:
        for e in engines:
            await e.dispose()
    assert all(res.exit_code == 0 for res in results)
    assert await scalar(engine, "SELECT count(*) FROM ingestion_runs") == 3


async def test_concurrent_full_rounds_store_each_observation_once(clean_orbital):
    engine = clean_orbital
    engines = [create_async_engine(engine.url, poolclass=NullPool) for _ in range(2)]
    try:
        # Different products would collide on rows only through dedup; here two
        # rounds race on everything and one of them skips every product.
        results = await asyncio.gather(
            *(make_round(e, providers(RecordingTransport())).run() for e in engines)
        )
    finally:
        for e in engines:
            await e.dispose()
    statuses = sorted(r.status for res in results for r in res.runs)
    assert statuses.count("ok") == 5
    total = await scalar(engine, "SELECT count(*) FROM orbital_detections")
    inserted = await scalar(engine, "SELECT sum(records_inserted) FROM ingestion_runs")
    assert total == inserted
    assert (
        await scalar(engine, "SELECT count(*) - count(DISTINCT dedup_key) FROM orbital_detections")
        == 0
    )


# --- worker process ---------------------------------------------------------------------


def run_worker(database, extra_env, *args):
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": postgis.asyncpg_url(database),
        "PYTHONIOENCODING": "utf-8",
        "INGEST_HTTP_ATTEMPTS": "1",
        "INGEST_MIN_REQUEST_INTERVAL_SECONDS": "0",
        **extra_env,
    }
    return subprocess.run(
        [sys.executable, "-m", "app.orbital.worker", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


async def test_worker_without_key_exits_0_with_disabled_runs(clean_orbital, geo_database):
    done = run_worker(geo_database, {"NASA_FIRMS_MAP_KEY": "", "INPE_QUEIMADAS_ENABLED": "false"})
    assert done.returncode == 0, done.stderr
    summary = json.loads(done.stdout.strip().splitlines()[-1])
    assert summary["round"] == "finished"
    assert {r["status"] for r in summary["runs"]} == {"disabled"}
    assert len(summary["runs"]) == 5


async def test_worker_with_unreachable_provider_exits_2_and_hides_the_key(
    clean_orbital, geo_database
):
    done = run_worker(
        geo_database,
        {
            "NASA_FIRMS_MAP_KEY": FAKE_KEY,
            "NASA_FIRMS_BASE_URL": "http://127.0.0.1:9/api",  # nothing listens here
            "INPE_QUEIMADAS_ENABLED": "false",
            "INGEST_HTTP_TIMEOUT_SECONDS": "2",
        },
        "--source",
        "firms",
    )
    assert done.returncode == 2, done.stderr
    summary = json.loads(done.stdout.strip().splitlines()[-1])
    # Refused on Linux; on Windows the closed port times out. Both are honest.
    assert {r["error_code"] for r in summary["runs"]} <= {"connection_error", "timeout"}
    assert FAKE_KEY not in done.stdout + done.stderr
    async with clean_orbital.connect() as conn:
        params = (
            (await conn.execute(text("SELECT params::text FROM ingestion_runs"))).scalars().all()
        )
    assert params
    assert all(FAKE_KEY not in p for p in params)


async def test_worker_invalid_configuration_exits_3(geo_database):
    done = run_worker(geo_database, {"APP_ENV": "producao"})
    assert done.returncode == 3


# --- admin endpoint ------------------------------------------------------------------


@pytest.fixture
async def admin_api(clean_orbital, client):
    """The real router on the test database, as a real admin user."""
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.integrations import orbital_alerts_router as router
    from app.main import app
    from app.users.model import User

    engine = clean_orbital
    async with AsyncSession(engine, expire_on_commit=False) as session:
        admin = User(
            name="Admin Ingestão",
            email=f"admin-{uuid.uuid4().hex[:8]}@example.org",
            password_hash="x",  # never used to log in
            role="admin",
        )
        session.add(admin)
        await session.commit()

    async def _db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    transport = RecordingTransport()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[router.get_ingestion_engine] = lambda: engine
    app.dependency_overrides[router.get_ingestion_providers] = lambda: providers(transport)
    yield client, admin, engine
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": admin.id})
        await conn.execute(text("TRUNCATE orbital_detections, ingestion_runs"))
        await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": admin.id})


async def test_admin_ingest_returns_the_real_runs_and_audits_the_requester(admin_api):
    client, admin, engine = admin_api
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert len(body["runs"]) == 5
    assert {r["status"] for r in body["runs"]} == {"running"}
    assert "Nenhum resultado é afirmado" in body["message"]

    # The background task has finished by the time the ASGI call returns.
    for started in body["runs"]:
        run = (
            await client.get(f"/api/v1/orbital-alerts/ingestion-runs/{started['run_id']}")
        ).json()
        assert run["status"] == "ok"
        assert run["trigger"] == "manual"
        assert run["triggered_by_user_id"] == str(admin.id)
        assert run["params"]["round_id"] == body["round_id"]
        assert run["records_valid"] == FIXTURE_COUNTS[run["product"]]
    listed = (await client.get("/api/v1/orbital-alerts/ingestion-runs?limit=5")).json()
    assert {r["id"] for r in listed} == {r["run_id"] for r in body["runs"]}
    async with engine.connect() as conn:
        audit = (
            await conn.execute(
                text(
                    "SELECT user_id, actor_name, entity_id, metadata_json FROM audit_logs"
                    " WHERE action = 'orbital_ingest.requested'"
                )
            )
        ).one()
    assert audit.user_id == admin.id
    assert audit.entity_id == body["round_id"]
    assert len(audit.metadata_json["runs"]) == 5


async def test_admin_ingest_can_select_one_source(admin_api):
    client, _, _ = admin_api
    body = (await client.post("/api/v1/orbital-alerts/ingest", json={"sources": ["inpe"]})).json()
    assert [(r["source"], r["product"]) for r in body["runs"]] == [
        ("INPE_QUEIMADAS", "FOCOS_DIARIO_BR")
    ]


async def test_admin_ingest_reports_products_already_running(admin_api):
    client, _, engine = admin_api
    holder = make_round(engine, providers(RecordingTransport()))
    await holder.start()  # another live process owns every product
    try:
        body = (await client.post("/api/v1/orbital-alerts/ingest")).json()
    finally:
        await holder.abort("test_cleanup")
    assert body["status"] == "nothing_started"
    assert {r["status"] for r in body["runs"]} == {"skipped_active"}
    assert all(r["run_id"] is None for r in body["runs"])


async def test_unknown_run_is_404(admin_api):
    client, _, _ = admin_api
    response = await client.get(f"/api/v1/orbital-alerts/ingestion-runs/{uuid.uuid4()}")
    assert response.status_code == 404


# --- worker in process (same paths as the subprocess tests, measured) ----------------


def _worker_settings(database, **overrides):
    from app.config import Settings

    return Settings(
        app_env="test",
        database_url=postgis.asyncpg_url(database),
        ingest_http_attempts=1,
        ingest_min_request_interval_seconds=0,
        **overrides,
    )


def test_worker_main_reports_disabled_runs(geo_database, monkeypatch, capsys):
    from app.orbital import worker

    settings = _worker_settings(geo_database, nasa_firms_map_key="", inpe_queimadas_enabled=False)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    assert worker.main(["--source", "firms", "--window-hours", "2"]) == 0
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert [r["status"] for r in summary["runs"]] == ["disabled"] * 4


@pytest.fixture
def silent_server():
    """A TCP port that accepts connections and never answers (a hung provider)."""
    import socket

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(16)  # the kernel completes handshakes; nobody ever reads
    yield f"http://127.0.0.1:{server.getsockname()[1]}/api"
    server.close()


def test_worker_main_round_timeout_closes_runs(geo_database, monkeypatch, capsys, silent_server):
    from app.orbital import worker

    settings = _worker_settings(
        geo_database,
        nasa_firms_map_key=FAKE_KEY,
        nasa_firms_base_url=silent_server,
        inpe_queimadas_enabled=False,
        ingest_http_timeout_seconds=30,
        ingest_round_timeout_seconds=10,
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    assert worker.main(["--source", "firms"]) == 1
    output = capsys.readouterr().out
    summary = json.loads(output.strip().splitlines()[-1])
    assert summary["round"] == "timeout"
    assert FAKE_KEY not in output
    assert {r["status"] for r in summary["runs"]} == {"error"}
    assert {r["error_code"] for r in summary["runs"]} == {"interrupted"}


def test_worker_rejects_invalid_configuration(monkeypatch, capsys):
    from app.orbital import worker

    def broken():
        raise ValueError("APP_ENV inválido")

    monkeypatch.setattr("app.config.get_settings", broken)
    assert worker.main([]) == 3
    assert "Configuração inválida" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM is TerminateProcess on Windows")
async def test_sigterm_closes_the_runs_as_interrupted(clean_orbital, geo_database, silent_server):
    import signal
    import time

    child = subprocess.Popen(
        [sys.executable, "-m", "app.orbital.worker", "--source", "firms"],
        cwd=ROOT,
        env={
            **os.environ,
            "APP_ENV": "test",
            "DATABASE_URL": postgis.asyncpg_url(geo_database),
            "NASA_FIRMS_MAP_KEY": FAKE_KEY,
            "NASA_FIRMS_BASE_URL": silent_server,
            "INGEST_HTTP_ATTEMPTS": "1",
            "INGEST_MIN_REQUEST_INTERVAL_SECONDS": "0",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:  # wait until the worker owns its runs
            if await scalar(clean_orbital, "SELECT count(*) FROM ingestion_runs") == 4:
                break
            await asyncio.sleep(0.2)
        child.send_signal(signal.SIGTERM)
        out, _ = child.communicate(timeout=60)
    finally:
        if child.poll() is None:
            child.kill()
    assert child.returncode == 143
    assert json.loads(out.strip().splitlines()[-1])["round"] == "interrupted"
    runs = await runs_by_product(clean_orbital)
    assert {(r.status, r.error_code) for r in runs.values()} == {("error", "interrupted")}
    assert FAKE_KEY not in out


def test_worker_ingests_the_documented_inpe_fixture(
    clean_orbital, geo_database, monkeypatch, capsys
):
    """Validation without network: the historical sample is stored as what it is."""
    from app.orbital import worker
    from tests.orbital_support import INPE_SAMPLE

    settings = _worker_settings(geo_database, nasa_firms_map_key="")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    assert worker.main(["--inpe-fixture", str(INPE_SAMPLE)]) == 0
    first = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["runs"]
    assert [(r["product"], r["status"]) for r in first] == [("FOCOS_DIARIO_BR", "ok")]
    assert first[0]["records_inserted"] > 0
    assert worker.main(["--inpe-fixture", str(INPE_SAMPLE)]) == 0  # same file again
    again = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["runs"]
    assert again[0]["records_inserted"] == 0
    assert worker.main(["--inpe-fixture", "nao-existe.csv"]) == 3
    assert worker.main(["--inpe-fixture", str(INPE_SAMPLE.parent / "README.md")]) == 3


async def test_fixture_runs_are_marked_and_keep_original_times(clean_orbital, geo_database):
    from app.orbital.worker import fixture_round_inputs
    from tests.orbital_support import INPE_SAMPLE

    providers, window = fixture_round_inputs(INPE_SAMPLE)
    result = await IngestionRound(clean_orbital, providers, trigger="manual", window=window).run()
    assert result.runs[0].status == "ok"
    rows = await scalar(
        clean_orbital,
        "SELECT count(*) FROM ingestion_runs WHERE params->'provenance'->>'origin' = 'fixture'",
    )
    assert rows == 1
    days = await scalar(
        clean_orbital,
        "SELECT string_agg(DISTINCT to_char(observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD'), ',')"
        " FROM orbital_detections",
    )
    assert days == "2026-11-03"  # the sample's own day, never "today"
