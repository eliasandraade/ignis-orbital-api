"""Child process for the crash test: owns runs, then hangs inside a fetch.

    python tests/ingest_owner_process.py <asyncpg database url>

Prints the run ids once they exist, then blocks forever in the provider's
fetch (as if NASA never answered) until the parent kills it.
"""

import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.main  # noqa: F401 — registers every ORM mapper (runs → users)
from app.orbital.contracts import DetectionSource
from app.orbital.ingestion import IngestionRound


class HangingProvider:
    source = DetectionSource.NASA_FIRMS

    def products(self):
        return ("VIIRS_NOAA20_NRT",)

    async def fetch(self, product, window, bbox, *, previous=None):
        await asyncio.Event().wait()


async def main(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    ingestion = IngestionRound(engine, [HangingProvider()], trigger="schedule")
    runs = await ingestion.start()
    print(" ".join(str(r.run_id) for r in runs), flush=True)
    await ingestion.execute()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
