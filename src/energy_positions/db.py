"""Where the database is, and how a request gets a connection to it.

The pool is made once, when the app starts, and kept on app.state (see app.py).
Each request borrows one connection from it for as long as the request lasts.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import asyncpg
from fastapi import Request

# The database in compose.yaml: a local development container with throwaway values.
# 127.0.0.1 and not localhost: on Windows, localhost is tried over IPv6 first, the
# container is published on IPv4 only, and every new connection waits out the miss.
DEFAULT_DATABASE_URL = "postgresql://positions:positions@127.0.0.1:55432/positions"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def describe(url: str) -> str:
    """The database a URL points at, without the password, for printing."""
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port or 5432}{parts.path}"


async def get_connection(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """The FastAPI dependency: one connection per request.

    Everything before the yield runs before the endpoint, everything after it runs
    when the endpoint is done, and the connection goes back to the pool either way.
    """
    async with request.app.state.pool.acquire() as connection:
        yield connection
