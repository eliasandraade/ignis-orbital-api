"""Controlled HTTP doubles for the providers, backed by real public fixtures."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.orbital.contracts import TimeWindow

FIXTURES = Path(__file__).parent / "fixtures" / "orbital"
# The INPE sample ships in the image (local validation without network).
INPE_SAMPLE = (
    Path(__file__).parents[1] / "data" / "samples" / "inpe" / "focos_diario_br_20261103.csv"
)
FIRMS_PRODUCTS = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT")
FIXTURE_COUNTS = {
    "VIIRS_SNPP_NRT": 11,
    "VIIRS_NOAA20_NRT": 227,
    "VIIRS_NOAA21_NRT": 210,
    "MODIS_NRT": 133,
    "FOCOS_DIARIO_BR": 498,
}
INPE_FILE = "focos_diario_br_20261103.csv"
INPE_ETAG = '"208041-65f6aa5237380"'
# The fixtures' UTC day; a past day, so a missing file is an error, not "not yet".
WINDOW = TimeWindow(datetime(2026, 11, 3, 1, tzinfo=UTC), datetime(2026, 11, 3, 23, tzinfo=UTC))
FAKE_KEY = "f1rm5-test-key-0123456789abcdef"  # never a real credential


def fixture_bytes(product: str) -> bytes:
    if product == "FOCOS_DIARIO_BR":
        return INPE_SAMPLE.read_bytes()
    return (FIXTURES / f"firms_{product}.csv").read_bytes()


class RecordingTransport(httpx.AsyncBaseTransport):
    """Answers like FIRMS and INPE from the fixtures; records every request."""

    def __init__(self, override: Callable[[httpx.Request], httpx.Response | None] | None = None):
        self.requests: list[httpx.Request] = []
        self._override = override

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._override is not None:
            response = self._override(request)
            if response is not None:
                return response
        path = request.url.path
        for product in FIRMS_PRODUCTS:
            if f"/{product}/" in path:
                return httpx.Response(200, content=fixture_bytes(product))
        if path.endswith(INPE_FILE):
            if request.headers.get("if-none-match") == INPE_ETAG:
                return httpx.Response(304, headers={"etag": INPE_ETAG})
            return httpx.Response(
                200,
                content=fixture_bytes("FOCOS_DIARIO_BR"),
                headers={"etag": INPE_ETAG, "last-modified": "Wed, 04 Nov 2026 03:05:02 GMT"},
            )
        return httpx.Response(404, text="not found")
