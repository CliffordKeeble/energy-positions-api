"""Where the database is, and how a request gets a connection to it.

The pool is made once, when the app starts, and kept on app.state (see app.py).
Each request borrows one connection from it for as long as the request lasts.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import asyncpg
from fastapi import Request

# The database in compose.yaml: a local development container with throwaway values.
# 127.0.0.1 and not localhost: on Windows, localhost is tried over IPv6 first, the
# container is published on IPv4 only, and every new connection waits out the miss.
DEFAULT_DATABASE_URL = "postgresql://positions:positions@127.0.0.1:55432/positions"

# Query parameters that libpq understands and asyncpg does not. asyncpg sends any
# parameter it does not recognise to the server as a setting for the session, and
# PostgreSQL refuses to start a session with a setting it has never heard of:
#     unrecognized configuration parameter "channel_binding"
LIBPQ_ONLY = frozenset({"channel_binding"})


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def connect_arguments(url: str) -> tuple[str, dict[str, Any]]:
    """What to hand asyncpg for a database URL: the DSN, and any keyword arguments.

    A URL copied from Neon's console works as it is pasted:

    - `sslmode=require` is read by asyncpg itself, and kept;
    - `channel_binding=require` is libpq's alone, so it is taken out (see LIBPQ_ONLY);
    - a host with `-pooler` in its name is Neon's PgBouncer in transaction mode, where
      asyncpg's cache of prepared statements breaks, so the cache is turned off.

    Any other URL comes back as it went in.
    """
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(name, value) for name, value in query if name not in LIBPQ_ONLY]
    if len(kept) != len(query):
        url = parts._replace(query=urlencode(kept)).geturl()

    options: dict[str, Any] = {}
    if parts.hostname and "-pooler" in parts.hostname:
        options["statement_cache_size"] = 0
    return url, options


async def connect(url: str) -> asyncpg.Connection:
    """One connection, for the scripts. The app's pool is made in app.py."""
    dsn, options = connect_arguments(url)
    return await asyncpg.connect(dsn, **options)


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
