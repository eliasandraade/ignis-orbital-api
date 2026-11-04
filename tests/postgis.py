"""Throwaway PostGIS databases for integration tests.

IGNIS_TEST_POSTGIS_URL points at a maintenance database of a disposable
server (e.g. postgresql://ignis:pw@localhost:5432/postgres). Each fixture
creates its own database there and drops it afterwards; nothing else is
touched. Without the variable the tests are skipped, unless
IGNIS_REQUIRE_POSTGIS_TESTS=1 (CI), where a missing server is a failure.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("IGNIS_TEST_POSTGIS_URL", "")
REQUIRED = os.environ.get("IGNIS_REQUIRE_POSTGIS_TESTS") == "1"
BASELINE_REVISION = "438a82832b4f"  # last revision before the geo foundation


def require_postgis() -> None:
    if ADMIN_URL:
        return
    if REQUIRED:
        pytest.fail("IGNIS_REQUIRE_POSTGIS_TESTS=1 mas IGNIS_TEST_POSTGIS_URL não definido")
    pytest.skip("IGNIS_TEST_POSTGIS_URL não definido (testes de integração PostGIS)")


def _database_url(name: str) -> str:
    parts = urlsplit(ADMIN_URL)
    return urlunsplit(parts._replace(path=f"/{name}"))


def asyncpg_url(name: str) -> str:
    return _database_url(name).replace("postgresql://", "postgresql+asyncpg://", 1)


async def _admin(statement: str) -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(statement)
    finally:
        await conn.close()


def _run(statement: str) -> None:
    # A private loop: never touches the loop pytest-asyncio manages.
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_admin(statement))
    finally:
        loop.close()


def create_database() -> str:
    name = f"ignis_test_{uuid.uuid4().hex[:12]}"
    _run(f'CREATE DATABASE "{name}"')
    return name


def drop_database(name: str) -> None:
    _run(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def run_module(name: str, *args: str, database: str) -> subprocess.CompletedProcess:
    """Run `python -m <name>` against one test database, in a clean process."""
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": asyncpg_url(database),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-m", name, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=600,
    )


def alembic(*args: str, database: str) -> str:
    result = run_module("alembic", *args, database=database)
    if result.returncode != 0:
        raise AssertionError(f"alembic {' '.join(args)} falhou:\n{result.stderr}")
    return result.stdout + result.stderr
