"""The application.

    uv run uvicorn energy_positions.app:app

Uvicorn is the server; this module hands it the ASGI app to serve.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from energy_positions import db
from energy_positions.routes import router


def create_app(database_url: str | None = None) -> FastAPI:
    """Build the app. A test passes the URL of its own database; nothing else does."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Runs once, around the whole life of the app: the pool is made before the
        # first request and closed after the last. Requests reach it through
        # app.state, and borrow one connection each (db.get_connection).
        app.state.pool = await asyncpg.create_pool(
            database_url or db.database_url(), min_size=1, max_size=10
        )
        try:
            yield
        finally:
            await app.state.pool.close()

    app = FastAPI(
        title="Energy positions",
        summary="Net energy positions by GB settlement period. A demo, on synthetic data.",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
