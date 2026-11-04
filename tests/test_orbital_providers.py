"""Sprint 1.2 — NASA FIRMS and INPE adapters (contract tests, no database).

HTTP is answered by tests/orbital_support.py from real public fixtures
(provenance in tests/fixtures/orbital/README.md); no test reaches NASA or INPE.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.orbital.contracts import CEARA_BBOX, DetectionSource, TimeWindow
from app.orbital.providers import providers_from_settings
from app.orbital.providers._http import (
    ProviderHttpError,
    RedactSecrets,
    RequestSpacer,
    RetryPolicy,
    get_with_retries,
)
from app.orbital.providers.firms import FirmsProvider, day_range, parse_row
from app.orbital.providers.inpe import InpeProvider, file_names
from app.orbital.providers.inpe import parse_row as inpe_parse_row
from tests.orbital_support import (
    FAKE_KEY,
    FIRMS_PRODUCTS,
    FIXTURE_COUNTS,
    INPE_ETAG,
    INPE_FILE,
    WINDOW,
    RecordingTransport,
    fixture_bytes,
)


class FakeSleep:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


@pytest.fixture
def sleep():
    return FakeSleep()


def firms(transport, sleep=None, key=FAKE_KEY, attempts=3):
    kwargs = {"sleep": sleep} if sleep is not None else {}
    return FirmsProvider(
        key,
        transport=transport,
        policy=RetryPolicy(attempts=attempts),
        spacer=RequestSpacer(0),
        **kwargs,
    )


def inpe(transport, enabled=True):
    return InpeProvider(enabled=enabled, transport=transport, spacer=RequestSpacer(0))


# --- NASA FIRMS: successful fetches from real fixtures -----------------------


@pytest.mark.parametrize("product", FIRMS_PRODUCTS)
async def test_firms_parses_every_row_of_the_real_fixture(product):
    transport = RecordingTransport()
    result = await firms(transport).fetch(product, WINDOW, CEARA_BBOX)
    assert result.status == "ok"
    assert len(result.detections) == FIXTURE_COUNTS[product]
    assert result.rejected == 0
    assert result.provenance["rows_received"] == FIXTURE_COUNTS[product]
    assert len(result.provenance["sha256"]) == 64
    (request,) = transport.requests
    assert request.url.path.endswith(f"/{product}/-41.5,-7.9,-37.2,-2.7/1/2026-11-03")


def test_viirs_row_keeps_class_confidence_and_i4_brightness():
    row = {
        "latitude": "-5.65729",
        "longitude": "-35.44393",
        "bright_ti4": "304.79",
        "scan": "0.41",
        "track": "0.37",
        "acq_date": "2026-11-02",
        "acq_time": "0336",
        "satellite": "N21",
        "confidence": "nominal",
        "version": "2.0NRT",
        "bright_ti5": "293.82",
        "frp": "1.15",
        "daynight": "N",
    }  # first data row of J2_VIIRS_C2_South_America_24h.csv
    detection = parse_row("VIIRS_NOAA21_NRT", row)
    assert detection.satellite == "NOAA-21"
    assert detection.instrument == "VIIRS"
    assert detection.observed_at == datetime(2026, 11, 2, 3, 36, tzinfo=UTC)
    assert detection.confidence == "nominal"
    assert detection.confidence_pct is None
    assert (detection.brightness_k, detection.brightness_channel) == (304.79, "VIIRS_I4")
    assert detection.frp_mw == 1.15
    assert detection.raw == row  # scan, track, version, bright_ti5 kept verbatim


def test_modis_confidence_is_a_percentage_never_mapped_to_a_class():
    row = {
        "latitude": "-25.03543",
        "longitude": "-58.54116",
        "brightness": "304.7",
        "scan": "3.45",
        "track": "1.75",
        "acq_date": "2026-11-02",
        "acq_time": "0121",
        "satellite": "T",
        "confidence": "61",
        "version": "6.1NRT",
        "bright_t31": "291.24",
        "frp": "32.1",
        "daynight": "N",
    }  # first data row of MODIS_C6_1_South_America_24h.csv
    detection = parse_row("MODIS_NRT", row)
    assert detection.satellite == "Terra"
    assert detection.confidence is None
    assert detection.confidence_pct == 61
    assert detection.brightness_channel == "MODIS_21_22"


async def test_firms_accepts_the_instrument_column_of_the_area_api():
    header, *rows = fixture_bytes("VIIRS_NOAA20_NRT").decode().splitlines()
    cols = header.split(",")
    cols.insert(8, "instrument")
    body = (
        ",".join(cols)
        + "\n"
        + "\n".join(",".join([*r.split(",")[:8], "VIIRS", *r.split(",")[8:]]) for r in rows)
    )
    transport = RecordingTransport(lambda r: httpx.Response(200, text=body))
    result = await firms(transport).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert result.status == "ok"
    assert len(result.detections) == 227


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"satellite": "N20"}, "satélite de outro produto"),
        ({"confidence": "medium"}, "classe VIIRS inexistente"),
        ({"latitude": "abc"}, "coordenada não numérica"),
        ({"longitude": "nan"}, "coordenada não finita"),
        ({"acq_time": "2575"}, "hora inexistente"),
        ({"acq_date": "03/11/2026"}, "data fora do formato"),
        ({"daynight": "X"}, "dia/noite inválido"),
        ({"frp": "-3"}, "FRP negativo"),
        ({"instrument": "MODIS"}, "instrumento de outro produto"),
    ],
)
def test_firms_rejects_rows_that_break_the_documented_format(change, reason):
    from app.orbital.providers.firms import RowError

    row = {
        "latitude": "-3.7",
        "longitude": "-38.5",
        "bright_ti4": "330",
        "acq_date": "2026-11-03",
        "acq_time": "0412",
        "satellite": "N21",
        "confidence": "n",
        "version": "2.0NRT",
        "frp": "2.1",
        "daynight": "N",
        **change,
    }
    with pytest.raises(RowError):
        parse_row("VIIRS_NOAA21_NRT", row)


async def test_firms_counts_bad_rows_as_rejected_and_keeps_the_rest():
    header, first, second, *_ = fixture_bytes("VIIRS_NOAA20_NRT").decode().splitlines()
    bad_time = first.split(",")
    bad_time[6] = "9999"
    body = "\n".join([header, first, ",".join(bad_time), "-3.7,-38.5", second]) + "\n"
    transport = RecordingTransport(lambda r: httpx.Response(200, text=body))
    result = await firms(transport).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert result.status == "ok"
    assert len(result.detections) == 2
    assert result.rejected == 2  # impossible time + truncated line


async def test_firms_header_only_is_a_real_empty_answer():
    header = fixture_bytes("VIIRS_SNPP_NRT").decode().splitlines()[0] + "\n"
    transport = RecordingTransport(lambda r: httpx.Response(200, text=header))
    result = await firms(transport).fetch("VIIRS_SNPP_NRT", WINDOW, CEARA_BBOX)
    assert (result.status, result.detections, result.rejected) == ("ok", (), 0)


# --- NASA FIRMS: failures ------------------------------------------------------


async def test_firms_without_key_is_disabled_and_makes_no_request():
    transport = RecordingTransport()
    result = await firms(transport, key="").fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert result.status == "disabled"
    assert result.error_code == "missing_api_key"
    assert result.detections == ()
    assert transport.requests == []


async def test_firms_rejected_key_is_unavailable():
    # Observed on 2026-11-04: an invalid key answers HTTP 400 "Invalid MAP_KEY.".
    transport = RecordingTransport(lambda r: httpx.Response(400, text="Invalid MAP_KEY."))
    result = await firms(transport).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert (result.status, result.error_code) == ("unavailable", "auth_rejected")
    assert result.detections == ()


@pytest.mark.parametrize(
    "body",
    [
        "<html><body>Service Unavailable</body></html>",
        "Invalid MAP_KEY.",
        "latitude,longitude\n-3.7,-38.5\n",  # missing documented columns
        "",
    ],
)
async def test_firms_non_csv_answer_is_unavailable_not_zero_fires(body):
    transport = RecordingTransport(lambda r: httpx.Response(200, text=body))
    result = await firms(transport).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert (result.status, result.error_code) == ("unavailable", "invalid_csv")
    assert result.detections == ()


async def test_firms_retries_5xx_with_exponential_backoff(sleep):
    answers = iter([503, 502])

    def flaky(request):
        status = next(answers, None)
        return httpx.Response(status) if status else None

    transport = RecordingTransport(flaky)
    result = await firms(transport, sleep).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert result.status == "ok"
    assert len(transport.requests) == 3
    assert sleep.delays == [2.0, 4.0]


async def test_firms_gives_up_after_the_retry_budget(sleep):
    transport = RecordingTransport(lambda r: httpx.Response(503))
    result = await firms(transport, sleep).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert (result.status, result.error_code) == ("unavailable", "http_503")
    assert len(transport.requests) == 3


async def test_firms_rate_limit_honours_retry_after(sleep):
    answers = iter([httpx.Response(429, headers={"retry-after": "7"})])
    transport = RecordingTransport(lambda r: next(answers, None))
    result = await firms(transport, sleep).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert result.status == "ok"
    assert sleep.delays == [7.0]


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (httpx.ReadTimeout("read timed out"), "timeout"),
        (httpx.ConnectError("connection refused"), "connection_error"),
    ],
)
async def test_firms_transport_failures_are_unavailable(sleep, exc, code):
    def boom(request):
        raise exc

    transport = RecordingTransport(boom)
    result = await firms(transport, sleep).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
    assert (result.status, result.error_code) == ("unavailable", code)
    assert len(transport.requests) == 3


# --- credentials ---------------------------------------------------------------


async def test_map_key_never_leaves_the_request(sleep, caplog):
    caplog.set_level(logging.DEBUG)
    leaks = []

    def boom(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")  # text carries the key

    for transport in (
        RecordingTransport(boom),
        RecordingTransport(lambda r: httpx.Response(400, text="Invalid MAP_KEY.")),
        RecordingTransport(lambda r: httpx.Response(500, text=str(r.url))),
        RecordingTransport(),
    ):
        result = await firms(transport, sleep).fetch("VIIRS_NOAA20_NRT", WINDOW, CEARA_BBOX)
        assert FAKE_KEY in str(transport.requests[0].url)  # the key was really used...
        leaks.append(json.dumps(result.provenance) + str(result.error_code) + repr(result))
    assert all(FAKE_KEY not in text for text in leaks)  # ...and appears nowhere else
    assert FAKE_KEY not in caplog.text


async def test_transport_error_code_has_no_url():
    def boom(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    url, policy, spacer = f"https://x/{FAKE_KEY}", RetryPolicy(attempts=1), RequestSpacer(0)
    async with httpx.AsyncClient(transport=RecordingTransport(boom)) as client:
        with pytest.raises(ProviderHttpError) as info:
            await get_with_retries(
                client,
                url,
                policy=policy,
                spacer=spacer,
            )
    assert str(info.value) == "connection_error"
    assert info.value.__cause__ is None
    assert info.value.__context__ is None  # the httpx error (with URL) is not attached


def test_redact_filter_masks_configured_secrets():
    record = logging.LogRecord(
        "x", logging.INFO, "", 0, "GET /api/area/csv/%s/x", (FAKE_KEY,), None
    )
    RedactSecrets([FAKE_KEY, ""]).filter(record)
    assert record.getMessage() == "GET /api/area/csv/***/x"


# --- request spacing and windows ----------------------------------------------


async def test_request_spacer_enforces_a_minimum_interval():
    now = [100.0]
    waits = []

    async def fake_sleep(delay):
        waits.append(delay)
        now[0] += delay

    spacer = RequestSpacer(1.5, clock=lambda: now[0], sleep=fake_sleep)
    await spacer.wait()
    now[0] += 0.5
    await spacer.wait()
    assert waits == [1.0]


def test_firms_day_range_covers_every_utc_day_of_the_window():
    assert day_range(WINDOW) == ("2026-11-03", 1)
    two_days = TimeWindow(
        datetime(2026, 11, 2, 22, tzinfo=UTC), datetime(2026, 11, 3, 2, tzinfo=UTC)
    )
    assert day_range(two_days) == ("2026-11-02", 2)
    week = TimeWindow.last(timedelta(days=7), now=datetime(2026, 11, 10, tzinfo=UTC))
    assert day_range(week) == ("2026-11-06", 5)  # FIRMS accepts at most 5 days


# --- INPE -----------------------------------------------------------------------


async def test_inpe_parses_the_real_daily_file_inside_the_bbox():
    transport = RecordingTransport()
    result = await inpe(transport).fetch("FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX)
    assert result.status == "ok"
    assert len(result.detections) == 498
    assert result.rejected == 0
    (info,) = result.provenance["files"]
    assert info["name"] == INPE_FILE
    assert (info["rows_in_file"], info["rows_outside_bbox"]) == (511, 13)
    assert info["etag"] == INPE_ETAG
    assert len(info["sha256"]) == 64
    first = result.detections[0]
    assert first.source is DetectionSource.INPE_QUEIMADAS
    assert first.provider_record_id == first.raw["id"]
    assert first.observed_at.tzinfo is UTC
    # INPE publishes no confidence, brightness or documented FRP unit here.
    assert {
        (d.confidence, d.confidence_pct, d.brightness_k, d.frp_mw) for d in result.detections
    } == {(None, None, None, None)}


async def test_inpe_unchanged_file_is_not_downloaded_again():
    transport = RecordingTransport()
    first = await inpe(transport).fetch("FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX)
    again = await inpe(transport).fetch(
        "FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX, previous=first.provenance
    )
    assert transport.requests[1].headers["if-none-match"] == INPE_ETAG
    assert (again.status, again.detections) == ("ok", ())
    assert again.provenance["files"][0] == {"name": INPE_FILE, "status": 304, "etag": INPE_ETAG}
    third = await inpe(transport).fetch(
        "FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX, previous=again.provenance
    )
    assert transport.requests[2].headers["if-none-match"] == INPE_ETAG  # still conditional
    assert third.detections == ()


async def test_inpe_missing_past_file_is_unavailable_but_today_may_not_exist_yet():
    transport = RecordingTransport(lambda r: httpx.Response(404))
    past = await inpe(transport).fetch("FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX)
    assert (past.status, past.error_code) == ("unavailable", "http_404")
    today = TimeWindow.last(timedelta(hours=1))
    if today.start.date() == today.end.date():
        current = await inpe(transport).fetch("FOCOS_DIARIO_BR", today, CEARA_BBOX)
        assert (current.status, current.detections) == ("ok", ())


@pytest.mark.parametrize(
    "body",
    [
        b"<html>erro</html>",
        b"lat,lon\n-3.7,-38.5\n",
        b"\xff\xfe\x00not utf-8",
    ],
)
async def test_inpe_malformed_file_is_unavailable(body):
    transport = RecordingTransport(lambda r: httpx.Response(200, content=body))
    result = await inpe(transport).fetch("FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX)
    assert (result.status, result.error_code) == ("unavailable", "invalid_csv")
    assert result.detections == ()


async def test_inpe_bad_rows_are_rejected_not_guessed():
    header, row, *_ = fixture_bytes("FOCOS_DIARIO_BR").decode().splitlines()
    inside = [
        line
        for line in fixture_bytes("FOCOS_DIARIO_BR").decode().splitlines()[1:]
        if "CEARÁ" in line
    ][0]
    no_time = inside.split(",")
    no_time[3] = ""
    bad_lat = inside.split(",")
    bad_lat[1] = "sul"
    body = "\n".join([header, inside, ",".join(no_time), ",".join(bad_lat), "x,y"]) + "\n"
    transport = RecordingTransport(lambda r: httpx.Response(200, text=body))
    result = await inpe(transport).fetch("FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX)
    assert len(result.detections) == 1
    assert result.rejected == 3


def test_inpe_unknown_satellite_is_kept_without_inventing_a_sensor():
    row = {
        "id": "x1",
        "lat": "-3.7",
        "lon": "-38.5",
        "data_hora_gmt": "2026-11-03 12:00:00",
        "satelite": "SAT-NOVO-1",
    }
    assert inpe_parse_row(row, -3.7, -38.5).instrument == "UNSPECIFIED"


async def test_inpe_disabled_makes_no_request():
    transport = RecordingTransport()
    result = await inpe(transport, enabled=False).fetch("FOCOS_DIARIO_BR", WINDOW, CEARA_BBOX)
    assert result.status == "disabled"
    assert transport.requests == []


def test_inpe_file_names_follow_the_utc_days_of_the_window():
    two_days = TimeWindow(
        datetime(2026, 11, 2, 20, tzinfo=UTC), datetime(2026, 11, 3, 2, tzinfo=UTC)
    )
    assert [n for n, _ in file_names(two_days)] == [
        "focos_diario_br_20261102.csv",
        "focos_diario_br_20261103.csv",
    ]


# --- deduplication stability and provider independence -----------------------


def test_dedup_key_is_stable_across_reserialisation():
    base = {
        "latitude": "-3.124850",
        "longitude": " -38.5",
        "bright_ti4": "330",
        "acq_date": "2026-11-03",
        "acq_time": "0412",
        "satellite": "N21",
        "confidence": "n",
        "version": "2.0NRT",
        "frp": "2.1",
        "daynight": "N",
    }
    variants = [
        base,
        {**base, "latitude": "-3.12485", "longitude": "-38.50000"},
        {**base, "acq_time": "412"},  # unpadded HHMM
        {**base, "confidence": "nominal", "version": "2.0URT"},  # not part of identity
    ]
    keys = {parse_row("VIIRS_NOAA21_NRT", v).dedup_key for v in variants}
    assert len(keys) == 1


def test_same_place_and_time_from_two_providers_are_two_records():
    firms_row = {
        "latitude": "-6.0737",
        "longitude": "-39.479",
        "bright_ti4": "330",
        "acq_date": "2026-11-03",
        "acq_time": "0012",
        "satellite": "N20",
        "confidence": "n",
        "version": "2.0NRT",
        "frp": "2.1",
        "daynight": "N",
    }
    inpe_row = {
        "id": "1e621901-969c-3909-aa0e-64d96f6a5da8",
        "lat": "-6.0737",
        "lon": "-39.479",
        "data_hora_gmt": "2026-11-03 00:12:00",
        "satelite": "NOAA-20",
    }
    a = parse_row("VIIRS_NOAA20_NRT", firms_row)
    b = inpe_parse_row(inpe_row, -6.0737, -39.479)
    assert a.dedup_key != b.dedup_key  # correlated observations, both preserved


# --- configuration ----------------------------------------------------------------


def test_providers_from_settings_keeps_firms_visible_without_a_key():
    from app.config import Settings

    settings = Settings(app_env="test", nasa_firms_map_key="", inpe_queimadas_enabled=False)
    providers = providers_from_settings(settings)
    assert [p.source for p in providers] == [
        DetectionSource.NASA_FIRMS,
        DetectionSource.INPE_QUEIMADAS,
    ]
    assert providers_from_settings(settings, sources=("inpe",))[0].products() == (
        "FOCOS_DIARIO_BR",
    )
