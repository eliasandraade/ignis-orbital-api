"""Sprint 1.3 — public read API over PostGIS (detections, sources, stats, IBGE).

Data is written by a real ingestion round (public fixtures through the
provider adapters); every assertion compares the HTTP answer with SQL run
directly on the same database.
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.orbital.ingestion import IngestionRound
from app.orbital.providers._http import RequestSpacer, RetryPolicy
from app.orbital.providers.firms import FirmsProvider
from app.orbital.providers.inpe import InpeProvider
from tests.orbital_support import FAKE_KEY, WINDOW, RecordingTransport

DAY = "from=2026-11-01T00:00:00Z&to=2026-11-05T00:00:00Z"


async def _no_sleep(_):
    return None


def _providers(transport, key=FAKE_KEY, inpe_origin="live"):
    common = {"transport": transport, "policy": RetryPolicy(attempts=1), "sleep": _no_sleep}
    return [
        FirmsProvider(key, spacer=RequestSpacer(0), **common),
        InpeProvider(origin=inpe_origin, spacer=RequestSpacer(0), **common),
    ]


async def _ingest(engine, transport=None, key=FAKE_KEY, inpe_origin="live"):
    providers = _providers(transport or RecordingTransport(), key, inpe_origin)
    return await IngestionRound(engine, providers, trigger="manual", window=WINDOW).run()


@pytest.fixture
async def api(clean_orbital, client):
    engine = clean_orbital

    async def _db():
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    return client, engine


async def _busiest_municipality(engine) -> str:
    rows = await _sql(
        engine,
        "SELECT j.ibge_code FROM orbital_detections d JOIN jurisdictions j"
        " ON j.id = d.jurisdiction_id GROUP BY j.ibge_code ORDER BY count(*) DESC, 1 LIMIT 1",
    )
    return rows[0][0]


async def _sql(engine, statement, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(statement), params)).all()


# --- detections -----------------------------------------------------------------------


async def test_list_returns_the_stored_rows_with_real_coordinates(api):
    client, engine = api
    await _ingest(engine)
    body = (await client.get(f"/api/v1/orbital-alerts?{DAY}&size=5000")).json()
    stored = await _sql(
        engine,
        "SELECT d.id::text, ST_Y(d.location), ST_X(d.location), j.ibge_code, d.observed_at"
        " FROM orbital_detections d JOIN jurisdictions j ON j.id = d.jurisdiction_id",
    )
    assert body["persisted"] is True
    assert body["data_origin"] == "postgis"
    assert body["total"] == len(stored) == len(body["items"])
    assert body["truncated"] is False
    by_id = {r[0]: r for r in stored}
    for item in body["items"]:
        _id, lat, lng, code, observed = by_id[item["id"]]
        assert (item["lat"], item["lng"]) == (lat, lng)  # the persisted point, unrounded
        assert item["jurisdiction"]["ibge_code"] == code
        assert datetime.fromisoformat(item["observed_at"]) == observed
        assert item["persisted"] is True
        assert "raw" not in item  # the list stays lean; raw is in the detail
    observed_times = [i["observed_at"] for i in body["items"]]
    assert observed_times == sorted(observed_times, reverse=True)


async def test_filters_match_sql(api):
    client, engine = api
    await _ingest(engine)
    code = await _busiest_municipality(engine)
    cases = {
        "source=INPE_QUEIMADAS": "d.source = 'INPE_QUEIMADAS'",
        "satellite=NOAA-20": "d.satellite = 'NOAA-20'",
        f"jurisdiction={code}": f"j.ibge_code = '{code}'",
        "bbox=-39.5,-7.9,-38.5,-6.5": "d.location && ST_MakeEnvelope(-39.5,-7.9,-38.5,-6.5,4326)",
    }
    for query, condition in cases.items():
        expected = (
            await _sql(
                engine,
                "SELECT count(*) FROM orbital_detections d JOIN jurisdictions j"
                " ON j.id = d.jurisdiction_id WHERE " + condition,
            )
        )[0][0]
        body = (await client.get(f"/api/v1/orbital-alerts?{DAY}&{query}&size=5000")).json()
        assert body["total"] == expected, query
        assert len(body["items"]) == expected, query


async def test_time_window_is_half_open_on_observed_at(api):
    client, engine = api
    await _ingest(engine)
    (first,) = await _sql(engine, "SELECT min(observed_at) FROM orbital_detections")
    start = first[0].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (first[0] + timedelta(seconds=1)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    expected = (
        await _sql(
            engine, "SELECT count(*) FROM orbital_detections WHERE observed_at = :t", t=first[0]
        )
    )[0][0]
    exact = (await client.get(f"/api/v1/orbital-alerts?from={start}&to={end}")).json()
    assert exact["total"] == expected > 0


async def test_pagination_reports_truncation(api):
    client, engine = api
    await _ingest(engine)
    page1 = (await client.get(f"/api/v1/orbital-alerts?{DAY}&size=50")).json()
    page2 = (await client.get(f"/api/v1/orbital-alerts?{DAY}&size=50&page=2")).json()
    assert len(page1["items"]) == 50
    assert page1["truncated"] is True
    assert page1["pages"] == -(-page1["total"] // 50)
    assert not {i["id"] for i in page1["items"]} & {i["id"] for i in page2["items"]}


async def test_detail_keeps_the_provider_row_and_404s_unknown_ids(api):
    client, engine = api
    await _ingest(engine)
    (row,) = await _sql(
        engine,
        "SELECT id::text, raw FROM orbital_detections WHERE source = 'INPE_QUEIMADAS' LIMIT 1",
    )
    detail = (await client.get(f"/api/v1/orbital-alerts/{row[0]}")).json()
    assert detail["raw"] == row[1]
    assert detail["provider_record_id"] == row[1]["id"]
    missing = await client.get("/api/v1/orbital-alerts/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


async def test_empty_window_is_distinguished_from_missing_data(api):
    client, engine = api
    before = (await client.get(f"/api/v1/orbital-alerts?{DAY}")).json()
    assert before["items"] == []
    assert {s["state"] for s in before["sources"]} == {"never_ingested"}
    await _ingest(engine)
    later = (
        await client.get("/api/v1/orbital-alerts?from=2026-10-01T00:00:00Z&to=2026-10-02T00:00:00Z")
    ).json()
    assert later["items"] == []
    states = {s["source"]: s["state"] for s in later["sources"]}
    assert states["INPE_QUEIMADAS"] in ("live", "stale")  # it was ingested: "no detections"


# --- source status ------------------------------------------------------------------------


async def test_source_status_separates_ingestion_from_observation_times(api):
    client, engine = api
    await _ingest(engine, key="")  # FIRMS without key
    sources = {s["source"]: s for s in (await client.get("/api/v1/orbital-alerts/sources")).json()}
    firms, inpe = sources["NASA_FIRMS"], sources["INPE_QUEIMADAS"]
    assert firms["state"] == "disabled"
    assert {p["state"] for p in firms["products"]} == {"disabled"}
    assert firms["last_success_at"] is None
    assert inpe["state"] == "live"
    assert inpe["origin"] == "live"
    # Ingested now; observed on 2026-11-03: two different clocks, both reported.
    assert inpe["latest_observation_at"].startswith("2026-11-03")
    assert inpe["last_success_at"] > inpe["latest_observation_at"]


async def test_source_becomes_stale_then_unavailable(api):
    client, engine = api
    await _ingest(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ingestion_runs SET started_at = started_at - interval '3 hours',"
                " finished_at = finished_at - interval '3 hours'"
            )
        )
    stale = {
        s["source"]: s["state"] for s in (await client.get("/api/v1/orbital-alerts/sources")).json()
    }
    assert stale == {"NASA_FIRMS": "stale", "INPE_QUEIMADAS": "stale"}
    failing = RecordingTransport(
        lambda r: httpx.Response(503) if "focos_diario" in r.url.path else None
    )
    await _ingest(engine, failing)
    after = {s["source"]: s for s in (await client.get("/api/v1/orbital-alerts/sources")).json()}
    assert after["INPE_QUEIMADAS"]["state"] == "unavailable"
    assert after["INPE_QUEIMADAS"]["products"][0]["last_error_code"] == "http_503"
    assert after["NASA_FIRMS"]["state"] == "live"


async def test_fixture_origin_is_reported(api):
    client, engine = api
    await _ingest(engine, key="", inpe_origin="fixture")
    inpe = [
        s
        for s in (await client.get("/api/v1/orbital-alerts/sources")).json()
        if s["source"] == "INPE_QUEIMADAS"
    ][0]
    assert inpe["origin"] == "fixture"
    assert "não dados atuais" in inpe["message"]


# --- stats -----------------------------------------------------------------------------------


async def test_stats_are_consistent_with_the_list(api):
    client, engine = api
    await _ingest(engine)
    code = await _busiest_municipality(engine)
    for query in ("", "&source=NASA_FIRMS", f"&jurisdiction={code}"):
        stats = (await client.get(f"/api/v1/orbital-alerts/stats?{DAY}{query}")).json()
        listing = (await client.get(f"/api/v1/orbital-alerts?{DAY}{query}&size=1")).json()
        assert stats["total"] == listing["total"]
        assert sum(b["count"] for b in stats["by_source"]) == stats["total"]
        assert sum(b["count"] for b in stats["by_satellite"]) == stats["total"]
        assert sum(b["count"] for b in stats["by_day"]) == stats["total"]
    full = (await client.get(f"/api/v1/orbital-alerts/stats?{DAY}")).json()
    (expected,) = await _sql(
        engine, "SELECT count(DISTINCT jurisdiction_id) FROM orbital_detections"
    )
    assert full["municipalities_with_detections"] == expected[0]
    counts = [m["count"] for m in full["top_municipalities"]]
    assert counts == sorted(counts, reverse=True)
    assert len(counts) <= 10


# --- jurisdictions ----------------------------------------------------------------------------


async def test_municipalities_are_the_official_184_with_counts(api):
    client, engine = api
    await _ingest(engine)
    body = (await client.get(f"/api/v1/jurisdictions/municipalities?{DAY}")).json()
    assert body["total"] == 184
    assert body["dataset"]["version"] == "2025"
    assert body["dataset"]["reference_date"] == "2025-04-30"
    names = {m["ibge_code"]: m["name"] for m in body["items"]}
    assert names["2304400"] == "Fortaleza"
    total = (await client.get(f"/api/v1/orbital-alerts?{DAY}&size=1")).json()["total"]
    assert sum(m["detections"] for m in body["items"]) == total


async def test_geojson_is_official_and_cacheable(api):
    client, _ = api
    response = await client.get("/api/v1/jurisdictions/geojson")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    collection = json.loads(response.text)
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 184
    assert collection["dataset"]["version"] == "2025"
    feature = next(f for f in collection["features"] if f["id"] == "2304400")
    assert feature["properties"]["name"] == "Fortaleza"
    assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
    ring = feature["geometry"]["coordinates"][0]
    lng, lat = ring[0][0] if feature["geometry"]["type"] == "MultiPolygon" else ring[0]
    assert -38.7 < lng < -38.3  # WGS 84 lon/lat order
    assert -3.9 < lat < -3.6
    cached = await client.get(
        "/api/v1/jurisdictions/geojson", headers={"If-None-Match": response.headers["etag"]}
    )
    assert cached.status_code == 304
    state = json.loads((await client.get("/api/v1/jurisdictions/geojson?level=state")).text)
    assert [f["id"] for f in state["features"]] == ["23"]
    full = json.loads(
        (await client.get("/api/v1/jurisdictions/geojson?level=state&tolerance=0")).text
    )

    def vertices(collection):
        return len(json.dumps(collection["features"][0]["geometry"]["coordinates"]).split("],"))

    assert vertices(full) > vertices(state)  # 0 = the official geometry, not simplified
    assert (await client.get("/api/v1/jurisdictions/geojson?tolerance=1")).status_code == 422


async def test_endpoints_report_missing_official_mesh(client, fresh_database):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from tests import postgis

    postgis.alembic("upgrade", "head", database=fresh_database)
    engine = create_async_engine(postgis.asyncpg_url(fresh_database), poolclass=NullPool)

    async def _db():
        async with AsyncSession(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    try:
        assert (await client.get("/api/v1/jurisdictions/geojson")).status_code == 503
        assert (await client.get("/api/v1/jurisdictions/municipalities")).status_code == 503
    finally:
        await engine.dispose()


@pytest.fixture
def fresh_database():
    from tests import postgis

    postgis.require_postgis()
    name = postgis.create_database()
    yield name
    postgis.drop_database(name)
