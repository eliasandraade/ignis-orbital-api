"""Scheduled ingestion worker: one round, then exit.

    python -m app.orbital.worker [--source firms|inpe ...] [--window-hours N]

Railway runs it as a cron service (entrypoint role `ingest`, every 15 min,
restart policy NEVER). Exit codes:
  0   every product ok, disabled or already running elsewhere
  1   our side failed: timeout, internal error, interrupted run
  2   a provider was unavailable or a run ended partial
  3   invalid configuration
  143 terminated by SIGTERM/SIGINT (the current run is closed as interrupted)
One JSON line summarises the round; no URL, key or credential is printed.
"""

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import sys
from datetime import timedelta

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.orbital.providers import SOURCES  # no settings at import time

EXIT_CONFIG = 3
EXIT_SIGNAL = 143


def configure_logging(secrets: list[str]) -> None:
    from app.orbital.providers._http import RedactSecrets

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    redact = RedactSecrets(secrets)
    for handler in logging.getLogger().handlers:
        handler.addFilter(redact)


async def run_once(settings, sources: tuple[str, ...], window_hours: int) -> int:
    # Imported only after the settings validated: app.main reads them at import.
    import app.main  # noqa: F401 — registers every ORM mapper (runs → users)
    from app.orbital.contracts import TimeWindow
    from app.orbital.ingestion import IngestionRound
    from app.orbital.providers import providers_from_settings

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    ingestion = IngestionRound(
        engine,
        providers_from_settings(settings, sources=sources),
        trigger="schedule",
        window=TimeWindow.last(timedelta(hours=window_hours)),
        product_timeout=settings.ingest_product_timeout_seconds,
    )
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _stop(*_):
        loop.call_soon_threadsafe(stop.set)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop)
        except (RuntimeError, ValueError):  # NotImplementedError on Windows
            signal.signal(sig, _stop)

    # The round runs in its own task; a signal or the deadline cancels that task,
    # which closes its runs as 'interrupted' before it ends.
    round_task = asyncio.create_task(ingestion.run())
    stop_task = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait(
            {round_task, stop_task},
            timeout=settings.ingest_round_timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        stop_task.cancel()
        if round_task.done():
            result = round_task.result()
            outcome, code = {"round": "finished", "exit_code": result.exit_code}, result.exit_code
        else:
            round_task.cancel()
            await asyncio.gather(round_task, return_exceptions=True)
            interrupted = stop.is_set()
            outcome = {"round": "interrupted" if interrupted else "timeout"}
            code = EXIT_SIGNAL if interrupted else 1
    finally:
        with contextlib.suppress(Exception):
            await engine.dispose()
    print(json.dumps({**outcome, "runs": [r.summary() for r in ingestion.runs]}))
    return code


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.orbital.worker")
    parser.add_argument("--source", action="append", choices=SOURCES)
    parser.add_argument("--window-hours", type=int)
    args = parser.parse_args(argv)
    try:
        from app.config import get_settings

        settings = get_settings()
    except Exception as exc:  # pydantic errors never include secret values here
        print(f"Configuração inválida: {type(exc).__name__}", file=sys.stderr)
        return EXIT_CONFIG
    configure_logging([settings.nasa_firms_map_key])
    window_hours = args.window_hours or settings.ingest_window_hours
    return asyncio.run(run_once(settings, tuple(args.source or SOURCES), window_hours))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
