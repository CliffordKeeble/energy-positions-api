"""The application.

    uv run uvicorn energy_positions.app:app --port 8048

Uvicorn is the server; this module hands it the ASGI app to serve.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from energy_positions import db
from energy_positions.routes import router

# Shown at the top of /docs. Measured on 15 Nov 2026: from `docker run` to the first
# answer from /docs took 2.3 to 2.4 seconds on one laptop, against a database that
# was already awake. The live service also has to fetch its image and wake its
# database, and neither could be timed here, so the figure is rounded up a long way.
DESCRIPTION = """\
All the data is **synthetic**: trades made up by a random number generator with a
fixed seed. No trade, price or portfolio here describes anything that happened.

The live service **sleeps when nobody is using it**, and so does its database. **The
first request after a quiet spell can take up to 30 seconds** while both wake up;
the requests after it are quick. (Measured locally, the container answers in under
3 seconds; the rest is a generous margin for fetching the image and waking the
database.)
"""


def create_app(database_url: str | None = None) -> FastAPI:
    """Build the app. A test passes the URL of its own database; nothing else does."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Runs once, around the whole life of the app: the pool is made before the
        # first request and closed after the last. Requests reach it through
        # app.state, and borrow one connection each (db.get_connection).
        dsn, options = db.connect_arguments(database_url or db.database_url())
        app.state.pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10, **options)
        try:
            yield
        finally:
            await app.state.pool.close()

    app = FastAPI(
        title="Energy positions",
        summary="Net energy positions by GB settlement period. A demo, on synthetic data.",
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.include_router(router)

    # TEMPORARY: until there is a front page, "/" sends a visitor to /docs. The
    # one-page front end will mount static files at "/" after the router, and a route
    # registered first answers first, so delete this route when that page lands.
    @app.get("/", include_in_schema=False)
    async def front_page() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    return app


app = create_app()
