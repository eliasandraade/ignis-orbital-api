"""Sprint 1.1 — integration against a real PostGIS (see tests/postgis.py)."""

import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.orbital import repository
from app.orbital.contracts import DetectionSource, NormalizedDetection, RunStatus, TimeWindow
from tests import postgis

NEW_TABLES = ("reference_datasets", "jurisdictions", "ingestion_runs", "orbital_detections")
T0 = datetime(2026, 9, 1, 15, 42, tzinfo=UTC)
FORTALEZA = (-3.7319, -38.5267)  # Praça do Ferreira
JUAZEIRO = (-7.2131, -39.3153)
TERESINA_PI = (-5.0892, -42.8019)  # outside Ceará
ATLANTIC = (-3.0, -38.0)  # offshore, outside every municipality


def detection(lat_lon, minute=0, satellite="N20", **overrides) -> NormalizedDetection:
    values = {
        "source": DetectionSource.NASA_FIRMS,
        "product": "VIIRS_NOAA20_NRT",
        "satellite": satellite,
        "instrument": "VIIRS",
        "observed_at": T0 + timedelta(minutes=minute),
        "latitude": lat_lon[0],
        "longitude": lat_lon[1],
        "confidence": "nominal",
        "frp_mw": 3.5,
        "brightness_k": 331.2,
        "brightness_channel": "VIIRS_I4",
        "daynight": "D",
        "raw": {"acq_time": "1542"},
    }
    return NormalizedDetection(**{**values, **overrides})


async def scalar(engine, sql: str, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar()


@pytest.fixture
def fresh_database():
    postgis.require_postgis()
    name = postgis.create_database()
    yield name
    postgis.drop_database(name)


# --- migrations --------------------------------------------------------------


def test_migration_upgrade_downgrade_upgrade(fresh_database):
    postgis.alembic("upgrade", postgis.BASELINE_REVISION, database=fresh_database)
    postgis.alembic("upgrade", "head", database=fresh_database)
    assert "a015 (head)" in postgis.alembic("current", database=fresh_database)
    postgis.alembic("downgrade", postgis.BASELINE_REVISION, database=fresh_database)
    out = postgis.run_module(
        "seed.jurisdictions", database=fresh_database
    )  # tables are gone: the importer must fail, not create them
    assert out.returncode != 0
    postgis.alembic("upgrade", "head", database=fresh_database)
    assert "a015 (head)" in postgis.alembic("current", database=fresh_database)


async def test_schema_matches_the_models(geo_engine):
    """`alembic check`, limited to this sprint's tables (older tables carry
    known drift documented in the delivery report)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.database import Base

    def diff(sync_conn):
        context = MigrationContext.configure(
            sync_conn,
            opts={
                "compare_type": True,
                "include_object": lambda obj, name, kind, reflected, other: (
                    (kind == "table" and name in NEW_TABLES)
                    or (
                        kind != "table"
                        and getattr(obj, "table", None) is not None
                        and obj.table.name in NEW_TABLES
                    )
                ),
            },
        )
        import app.geo.model  # noqa: F401
        import app.main  # noqa: F401
        import app.orbital.model  # noqa: F401

        return compare_metadata(context, Base.metadata)

    async with geo_engine.connect() as conn:
        assert await conn.run_sync(diff) == []


async def test_geometry_columns_srid_4326_and_gist_indexes(geo_engine):
    async with geo_engine.connect() as conn:
        columns = (
            await conn.execute(
                text(
                    "SELECT f_table_name, f_geometry_column, srid, type FROM geometry_columns"
                    " WHERE f_table_name IN ('jurisdictions', 'orbital_detections')"
                    " ORDER BY 1"
                )
            )
        ).all()
        gist = (
            (
                await conn.execute(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE indexdef LIKE '%USING gist%'"
                        " AND tablename IN ('jurisdictions', 'orbital_detections') ORDER BY 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        naive = (
            (
                await conn.execute(
                    text(
                        "SELECT table_name || '.' || column_name FROM information_schema.columns"
                        " WHERE table_name = ANY(:tables)"
                        " AND data_type = 'timestamp without time zone'"
                    ),
                    {"tables": list(NEW_TABLES)},
                )
            )
            .scalars()
            .all()
        )
    assert [tuple(c) for c in columns] == [
        ("jurisdictions", "geom", 4326, "MULTIPOLYGON"),
        ("orbital_detections", "location", 4326, "POINT"),
    ]
    assert gist == ["ix_jurisdictions_geom", "ix_orbital_detections_location"]
    assert naive == []  # every timestamp of the new tables carries a time zone


# --- official boundaries -----------------------------------------------------


async def test_184_municipalities_and_the_state_were_imported(geo_engine):
    async with geo_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT level, count(*) AS n, bool_and(ST_IsValid(geom)) AS valid,"
                    " bool_and(ST_SRID(geom) = 4326) AS srid,"
                    " bool_and(left(ibge_code, 2) = '23') AS in_ce,"
                    " sum(official_area_km2) AS area"
                    " FROM jurisdictions GROUP BY level ORDER BY level"
                )
            )
        ).all()
        orphans = await conn.scalar(
            text(
                "SELECT count(*) FROM jurisdictions m"
                " LEFT JOIN jurisdictions s ON s.id = m.parent_id AND s.level = 'state'"
                " WHERE m.level = 'municipality' AND s.id IS NULL"
            )
        )
    by_level = {r.level: r for r in rows}
    assert by_level["municipality"].n == 184
    assert by_level["state"].n == 1
    assert all(r.valid and r.srid and r.in_ce for r in rows)
    assert orphans == 0
    # Official areas (AREA_KM2) of the municipalities add up to the state's.
    assert abs(by_level["municipality"].area - by_level["state"].area) < 0.1


async def test_municipalities_tile_the_state_polygon(geo_engine):
    gap_km2 = await scalar(
        geo_engine,
        "WITH u AS (SELECT ST_Union(geom) g FROM jurisdictions WHERE level = 'municipality'),"
        " s AS (SELECT geom g FROM jurisdictions WHERE level = 'state')"
        " SELECT ST_Area(ST_SymDifference(u.g, s.g)::geography) / 1e6 FROM u, s",
    )
    overlap_km2 = await scalar(
        geo_engine,
        "SELECT coalesce(sum(ST_Area(ST_Intersection(a.geom, b.geom)::geography)), 0) / 1e6"
        " FROM jurisdictions a JOIN jurisdictions b ON a.ibge_code < b.ibge_code"
        " AND ST_Intersects(a.geom, b.geom)"
        " WHERE a.level = 'municipality' AND b.level = 'municipality'",
    )
    assert gap_km2 < 0.01
    assert overlap_km2 < 0.01


async def test_known_points_fall_in_the_right_municipality(geo_engine):
    lookup = (
        "SELECT ibge_code FROM jurisdictions WHERE level = 'municipality'"
        " AND ST_Covers(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))"
    )
    for (lat, lon), code in ((FORTALEZA, "2304400"), (JUAZEIRO, "2307304")):
        assert await scalar(geo_engine, lookup, lat=lat, lon=lon) == code
    assert await scalar(geo_engine, lookup, lat=TERESINA_PI[0], lon=TERESINA_PI[1]) is None


async def test_dataset_provenance_is_recorded(geo_engine):
    async with geo_engine.connect() as conn:
        dataset = (await conn.execute(text("SELECT * FROM reference_datasets"))).one()
        attributes = await conn.scalar(
            text("SELECT source_attributes FROM jurisdictions WHERE ibge_code = '2304400'")
        )
        audits = await conn.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action = 'jurisdictions.imported'")
        )
    assert (dataset.source, dataset.product, dataset.version) == (
        "IBGE",
        "Malha Municipal Digital",
        "2025",
    )
    assert dataset.reference_date.isoformat() == "2025-04-30"
    assert dataset.source_crs == "EPSG:4674"
    assert dataset.feature_count == 185
    assert {f["name"] for f in dataset.files} == {"CE_Municipios_2025.zip", "CE_UF_2025.zip"}
    assert attributes["NM_MUN"] == "Fortaleza"
    assert attributes["CD_MUN"] == "2304400"
    assert audits >= 1


async def test_reimport_is_idempotent_and_restores_drift(geo_engine):
    from app.geo.ibge_import import import_state

    async with geo_engine.begin() as conn:
        before = (
            await conn.execute(text("SELECT ibge_code, id, updated_at FROM jurisdictions"))
        ).all()
        await conn.execute(
            text("UPDATE jurisdictions SET name = 'Nome adulterado' WHERE ibge_code = '2304400'")
        )

    async with AsyncSession(geo_engine) as session:
        repaired = await import_state(session)
        await session.commit()
    async with AsyncSession(geo_engine) as session:
        again = await import_state(session)
        await session.commit()

    assert (repaired.inserted, repaired.updated, repaired.unchanged) == (0, 1, 184)
    assert (again.inserted, again.updated, again.unchanged) == (0, 0, 185)
    assert not again.dataset_created
    assert again.not_in_dataset == []
    async with geo_engine.connect() as conn:
        after = (
            await conn.execute(text("SELECT ibge_code, id, updated_at FROM jurisdictions"))
        ).all()
        name = await conn.scalar(text("SELECT name FROM jurisdictions WHERE ibge_code = '2304400'"))
        datasets = await conn.scalar(text("SELECT count(*) FROM reference_datasets"))
    assert name == "Fortaleza"
    assert datasets == 1
    ids_before = {r.ibge_code: r.id for r in before}
    assert {r.ibge_code: r.id for r in after} == ids_before  # rows kept, never recreated
    untouched = {r.ibge_code: r.updated_at for r in before if r.ibge_code != "2304400"}
    assert {r.ibge_code: r.updated_at for r in after if r.ibge_code != "2304400"} == untouched


async def test_concurrent_first_imports_store_everything_once(fresh_database):
    from app.geo.ibge_import import import_state

    postgis.alembic("upgrade", "head", database=fresh_database)
    engines = [
        create_async_engine(postgis.asyncpg_url(fresh_database), poolclass=NullPool)
        for _ in range(2)
    ]

    async def run(engine):
        async with AsyncSession(engine) as session:
            report = await import_state(session)
            await session.commit()
            return report

    try:
        reports = await asyncio.gather(*(run(e) for e in engines))
        totals = sorted((r.inserted, r.unchanged) for r in reports)
        assert totals == [(0, 185), (185, 0)]
        assert sorted(r.dataset_created for r in reports) == [False, True]
        assert await scalar(engines[0], "SELECT count(*) FROM jurisdictions") == 185
        assert await scalar(engines[0], "SELECT count(*) FROM reference_datasets") == 1
    finally:
        for engine in engines:
            await engine.dispose()


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        # Self-intersecting "bow tie": invalid geometry.
        (
            "UPDATE jurisdictions SET geom = ST_Multi(ST_GeomFromText("
            "'POLYGON((-39 -5, -38 -4, -38 -5, -39 -4, -39 -5))', 4326))"
            " WHERE ibge_code = '2304400'",
            "ck_jurisdictions_geom_valid",
        ),
        (
            "UPDATE jurisdictions SET parent_id = NULL WHERE ibge_code = '2304400'",
            "ck_jurisdictions_code_matches_level",
        ),
        (
            "UPDATE jurisdictions SET state_ibge_code = '22' WHERE ibge_code = '2304400'",
            "ck_jurisdictions_code_in_state",
        ),
        ("DELETE FROM reference_datasets", "jurisdictions_dataset_id_fkey"),
        ("DELETE FROM jurisdictions WHERE level = 'state'", "jurisdictions_parent_id_fkey"),
    ],
)
async def test_boundary_integrity_is_enforced_by_the_database(geo_engine, statement, constraint):
    sql = text(statement)
    async with geo_engine.connect() as conn:
        with pytest.raises(IntegrityError, match=constraint):
            await conn.execute(sql)
        await conn.rollback()


async def test_wrong_srid_is_refused_by_the_column_type(geo_engine):
    sql = text("UPDATE jurisdictions SET geom = ST_SetSRID(geom, 4674) WHERE ibge_code = '2304400'")
    async with geo_engine.connect() as conn:
        with pytest.raises(DBAPIError, match="SRID"):
            await conn.execute(sql)
        await conn.rollback()


# --- ingestion runs and detections -------------------------------------------


async def start(session, product="VIIRS_NOAA20_NRT"):
    return await repository.start_run(
        session,
        DetectionSource.NASA_FIRMS,
        product,
        trigger="schedule",
        window=TimeWindow.last(timedelta(days=1), now=T0 + timedelta(hours=1)),
        params={"bbox": [-41.5, -7.9, -37.2, -2.7]},
    )


async def test_batch_counters_match_what_was_written(clean_orbital):
    engine = clean_orbital
    batch = [
        detection(FORTALEZA),
        detection(JUAZEIRO, minute=1),
        detection(FORTALEZA),  # same observation twice in one batch
        detection(TERESINA_PI, minute=2),  # Piauí: out of scope
        detection(ATLANTIC, minute=3),  # sea: out of scope
    ]
    async with AsyncSession(engine) as session:
        run = await start(session)
        result = await repository.persist_batch(session, run.id, batch, rejected=2)
        await repository.finish_run(session, run.id, RunStatus.OK)
        await session.commit()

    assert result == repository.BatchResult(
        fetched=7, valid=5, rejected=2, out_of_scope=2, inserted=2, duplicate=1
    )
    async with engine.connect() as conn:
        stored = (
            await conn.execute(
                text(
                    "SELECT r.status, r.finished_at, r.records_fetched, r.records_valid,"
                    " r.records_rejected, r.records_out_of_scope, r.records_inserted,"
                    " r.records_duplicate,"
                    " (SELECT count(*) FROM orbital_detections d"
                    "  WHERE d.ingestion_run_id = r.id) AS rows_written"
                    " FROM ingestion_runs r"
                )
            )
        ).one()
        located = (
            await conn.execute(
                text(
                    "SELECT j.ibge_code, d.observed_at, ST_SRID(d.location) AS srid"
                    " FROM orbital_detections d JOIN jurisdictions j ON j.id = d.jurisdiction_id"
                    " ORDER BY d.observed_at"
                )
            )
        ).all()
    assert stored.status == "ok"
    assert stored.finished_at is not None
    assert stored[2:8] == (7, 5, 2, 2, 2, 1)
    assert stored.rows_written == stored.records_inserted == 2
    assert [(r.ibge_code, r.srid) for r in located] == [("2304400", 4326), ("2307304", 4326)]
    assert located[0].observed_at == T0
    assert located[0].observed_at.tzinfo is not None


async def test_reprocessing_a_window_writes_nothing(clean_orbital):
    engine = clean_orbital
    batch = [detection(FORTALEZA), detection(JUAZEIRO, minute=1)]
    for expected_inserted in (2, 0):
        async with AsyncSession(engine) as session:
            run = await start(session)
            result = await repository.persist_batch(session, run.id, batch)
            await repository.finish_run(session, run.id, RunStatus.OK)
            await session.commit()
        assert result.inserted == expected_inserted
        assert result.duplicate == 2 - expected_inserted
    assert await scalar(engine, "SELECT count(*) FROM orbital_detections") == 2


async def test_only_one_running_execution_per_product(clean_orbital):
    engine = clean_orbital
    async with AsyncSession(engine) as first:
        run_id = (await start(first)).id
        await first.commit()
    async with AsyncSession(engine) as second:
        with pytest.raises(repository.RunAlreadyActiveError):
            await start(second)
        other_id = (await start(second, product="MODIS_NRT")).id  # another product may run
        await second.commit()
    async with AsyncSession(engine) as session:
        await repository.finish_run(session, run_id, RunStatus.UNAVAILABLE, error_code="http_503")
        await repository.finish_run(session, other_id, RunStatus.DISABLED)
        await session.commit()
        again_id = (await start(session)).id  # a finished run frees the slot
        await session.commit()
    assert again_id != run_id


async def test_finished_runs_are_frozen(clean_orbital):
    engine = clean_orbital
    async with AsyncSession(engine) as session:
        run_id = (await start(session)).id
        await repository.finish_run(session, run_id, RunStatus.PARTIAL, error_message="x" * 900)
        await session.commit()
        late = [detection(FORTALEZA)]
        with pytest.raises(repository.RunNotActiveError):
            await repository.persist_batch(session, run_id, late)
        await session.rollback()
        with pytest.raises(repository.RunNotActiveError):
            await repository.finish_run(session, run_id, RunStatus.OK)
        await session.rollback()
        with pytest.raises(ValueError):
            await repository.finish_run(session, run_id, RunStatus.RUNNING)
    assert len(await scalar(engine, "SELECT error_message FROM ingestion_runs")) == 500


async def test_batch_must_match_the_run_source(clean_orbital):
    async with AsyncSession(clean_orbital) as session:
        run = await start(session)
        inpe = detection(FORTALEZA, source=DetectionSource.INPE_QUEIMADAS)
        with pytest.raises(ValueError, match="INPE_QUEIMADAS"):
            await repository.persist_batch(session, run.id, [inpe])
        with pytest.raises(ValueError):
            await repository.persist_batch(session, run.id, [], rejected=-1)


async def test_only_runs_whose_owner_is_gone_are_recovered(clean_orbital):
    """Liveness is the lease, not the clock: an old run whose owner still holds
    its connection is untouched; once that connection ends it is recovered."""
    engine = clean_orbital
    owner_engine = create_async_engine(engine.url, poolclass=NullPool)
    owner_conn = await owner_engine.connect()
    owner = AsyncSession(bind=owner_conn, expire_on_commit=False)
    run_id = uuid.uuid4()
    await repository.acquire_lease(owner, run_id)
    await repository.start_run(
        owner, DetectionSource.NASA_FIRMS, "VIIRS_NOAA20_NRT", trigger="schedule", run_id=run_id
    )
    await repository.persist_batch(owner, run_id, [detection(FORTALEZA)])
    await owner.commit()
    async with engine.begin() as conn:  # make it look ancient: irrelevant for liveness
        await conn.execute(text("UPDATE ingestion_runs SET started_at = now() - interval '2 days'"))

    async with AsyncSession(engine) as session:
        alive = await repository.recover_abandoned_runs(
            session, DetectionSource.NASA_FIRMS, "VIIRS_NOAA20_NRT"
        )
        await session.commit()
    assert alive == []

    await owner.close()
    await owner_conn.close()  # the owner "dies": PostgreSQL drops its lease
    await owner_engine.dispose()
    async with AsyncSession(engine) as session:
        recovered = await repository.recover_abandoned_runs(
            session, DetectionSource.NASA_FIRMS, "VIIRS_NOAA20_NRT"
        )
        await session.commit()
    assert recovered == [run_id]
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status, error_code, records_inserted FROM ingestion_runs")
            )
        ).one()
    assert tuple(row) == ("error", "abandoned", 1)  # what it committed stays counted


@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_concurrent_writers_never_double_count(clean_orbital, seed):
    """Overlapping batches in opposite, shuffled orders: no deadlock, no
    observation stored twice, and every run counts exactly what it wrote."""
    engine = clean_orbital
    shared = [detection(FORTALEZA, minute=m) for m in range(200)]
    only_a = [detection(JUAZEIRO, minute=m) for m in range(40)]
    only_b = [detection(FORTALEZA, minute=m, satellite="N21") for m in range(60)]
    batch_a, batch_b = shared + only_a, shared + only_b
    random.Random(seed).shuffle(batch_a)
    random.Random(-seed).shuffle(batch_b)
    engines = [create_async_engine(engine.url, poolclass=NullPool) for _ in range(2)]
    # Test-only: slow every row down so the two statements really overlap.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE FUNCTION test_slow_insert() RETURNS trigger LANGUAGE plpgsql AS"
                " $$ BEGIN PERFORM pg_sleep(0.002); RETURN NEW; END $$"
            )
        )
        await conn.execute(
            text(
                "CREATE TRIGGER test_slow_insert BEFORE INSERT ON orbital_detections"
                " FOR EACH ROW EXECUTE FUNCTION test_slow_insert()"
            )
        )

    async def writer(eng, product, batch):
        async with AsyncSession(eng) as session:
            run_id = (await start(session, product=product)).id
            await session.commit()
            for i in range(0, len(batch), 60):
                await repository.persist_batch(session, run_id, batch[i : i + 60])
                await session.commit()
            await repository.finish_run(session, run_id, RunStatus.OK)
            await session.commit()

    try:
        await asyncio.gather(
            writer(engines[0], "VIIRS_NOAA20_NRT", batch_a),
            writer(engines[1], "VIIRS_NOAA20_SP", batch_b),
        )
    finally:
        for eng in engines:
            await eng.dispose()
        async with engine.begin() as conn:
            await conn.execute(text("DROP TRIGGER test_slow_insert ON orbital_detections"))
            await conn.execute(text("DROP FUNCTION test_slow_insert()"))

    async with engine.connect() as conn:
        total = await conn.scalar(text("SELECT count(*) FROM orbital_detections"))
        runs = (
            await conn.execute(
                text(
                    "SELECT r.records_inserted, r.records_duplicate, r.records_valid,"
                    " (SELECT count(*) FROM orbital_detections d"
                    "  WHERE d.ingestion_run_id = r.id) AS written"
                    " FROM ingestion_runs r"
                )
            )
        ).all()
    assert total == 200 + 40 + 60
    assert sum(r.records_inserted for r in runs) == total
    assert sum(r.records_duplicate for r in runs) == 200
    assert all(r.records_inserted == r.written for r in runs)


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (
            "UPDATE ingestion_runs SET records_inserted = records_inserted + 1",
            "ck_ingestion_runs_valid_balance",
        ),
        (
            "UPDATE ingestion_runs SET records_fetched = records_fetched + 1",
            "ck_ingestion_runs_fetched_balance",
        ),
        ("UPDATE ingestion_runs SET status = 'ok'", "ck_ingestion_runs_finished_iff_final"),
        (
            "UPDATE ingestion_runs SET status = 'done', finished_at = now()",
            "ck_ingestion_runs_status_known",
        ),
        ("DELETE FROM ingestion_runs", "orbital_detections_ingestion_run_id_fkey"),
        (
            "DELETE FROM jurisdictions WHERE ibge_code = '2304400'",
            "orbital_detections_jurisdiction_id_fkey",
        ),
        (
            "UPDATE orbital_detections SET confidence = 'medium'",
            "ck_orbital_detections_confidence_known",
        ),
        (
            "UPDATE orbital_detections SET dedup_key = (SELECT min(dedup_key::text)::uuid"
            " FROM orbital_detections) ",
            "orbital_detections_dedup_key_key",
        ),
    ],
)
async def test_detection_integrity_is_enforced_by_the_database(
    clean_orbital, statement, constraint
):
    engine = clean_orbital
    async with AsyncSession(engine) as session:
        run = await start(session)
        await repository.persist_batch(
            session, run.id, [detection(FORTALEZA), detection(FORTALEZA, minute=5)]
        )
        await session.commit()
    sql = text(statement)
    async with engine.connect() as conn:
        with pytest.raises(IntegrityError, match=constraint):
            await conn.execute(sql)
        await conn.rollback()


async def test_point_on_a_shared_border_gets_the_lowest_ibge_code(clean_orbital):
    engine = clean_orbital
    async with engine.connect() as conn:
        point = (
            await conn.execute(
                text(
                    "SELECT ST_Y(p) AS lat, ST_X(p) AS lon FROM ("
                    " SELECT ST_PointN(ST_ExteriorRing(ST_GeometryN(a.geom, 1)), 1) AS p"
                    " FROM jurisdictions a WHERE a.ibge_code = '2304400') s"
                )
            )
        ).one()
        covering = (
            (
                await conn.execute(
                    text(
                        "SELECT ibge_code FROM jurisdictions WHERE level = 'municipality'"
                        " AND ST_Covers(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))"
                        " ORDER BY ibge_code"
                    ),
                    {"lat": point.lat, "lon": point.lon},
                )
            )
            .scalars()
            .all()
        )
    assert covering  # a vertex of Fortaleza's boundary is covered by Fortaleza at least
    async with AsyncSession(engine) as session:
        run = await start(session)
        await repository.persist_batch(session, run.id, [detection((point.lat, point.lon))])
        await session.commit()
    assigned = await scalar(
        engine,
        "SELECT j.ibge_code FROM orbital_detections d JOIN jurisdictions j"
        " ON j.id = d.jurisdiction_id",
    )
    assert assigned == covering[0]
