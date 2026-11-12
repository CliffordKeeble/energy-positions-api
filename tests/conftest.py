"""Fixtures for the tests that need the database (the ones marked `db`).

They run against a database of their own, positions_test, on the PostgreSQL server
in compose.yaml. It is created here if it is not there, its tables are rebuilt from
sql/schema.sql at the start of the run and emptied before each test. The seeded
database is never touched, so the tests pass whether or not the seed has been run.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from energy_positions.app import create_app
from energy_positions.settlement import SettlementPeriod

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://positions:positions@127.0.0.1:55432/positions_test"
)
SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


async def _rebuild_test_database() -> None:
    parts = urlsplit(TEST_DATABASE_URL)
    name = parts.path.lstrip("/")
    if not name.endswith("_test"):
        # These fixtures drop tables. They will only do it to a database that says it is for tests.
        raise RuntimeError(f"TEST_DATABASE_URL names the database {name!r}; it must end in '_test'")

    server = await asyncpg.connect(urlunsplit(parts._replace(path="/postgres")))
    try:
        if not await server.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await server.execute(f'CREATE DATABASE "{name}"')
    finally:
        await server.close()

    database = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await database.execute("DROP TABLE IF EXISTS trades, positions")
        await database.execute(SCHEMA.read_text(encoding="utf-8"))
    finally:
        await database.close()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    try:
        asyncio.run(_rebuild_test_database())
    except (OSError, asyncpg.PostgresError) as error:
        pytest.fail(
            "The tests marked 'db' need the PostgreSQL container. Start it with:\n"
            "    docker compose up -d --wait\n"
            'or run the pure tests alone with:  uv run pytest -m "not db"\n'
            f"({type(error).__name__}: {error})",
            pytrace=False,
        )
    return TEST_DATABASE_URL


@pytest.fixture
async def app(test_database_url: str) -> AsyncIterator[FastAPI]:
    """The real app, started and stopped the way the server does it, on empty tables."""
    app = create_app(test_database_url)
    async with app.router.lifespan_context(app):
        async with app.state.pool.acquire() as connection:
            await connection.execute("TRUNCATE trades, positions RESTART IDENTITY")
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client that calls the app in-process: no socket, no server to start."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def database(app: FastAPI) -> AsyncIterator[asyncpg.Connection]:
    """A connection of the test's own, for putting rows in and looking at them."""
    async with app.state.pool.acquire() as connection:
        yield connection


async def add_trade(
    connection: asyncpg.Connection, portfolio_id: int, period: SettlementPeriod, volume_mwh: str
) -> None:
    """Put a trade straight into the trades table, bypassing the API."""
    await connection.execute(
        "INSERT INTO trades (portfolio_id, period_start, volume_mwh, price, traded_at) "
        "VALUES ($1, $2, $3, $4, $5)",
        portfolio_id,
        period.start_utc,
        Decimal(volume_mwh),
        Decimal("50.00"),
        period.start_utc - timedelta(hours=2),
    )
