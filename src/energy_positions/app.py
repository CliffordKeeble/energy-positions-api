"""The application.

    uv run uvicorn energy_positions.app:app --port 8048

Uvicorn is the server; this module hands it the ASGI app to serve. If the one-page
front end has been built (web/, see the README), the same app serves it at "/".
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

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


# Uvicorn's own logger, so that a line written here is shown by `uvicorn` with no
# logging set up of ours.
log = logging.getLogger("uvicorn.error")

# Where the built page is looked for when nothing says: web/dist, beside src/. That is
# right in a checkout, where `uv sync` installs the package as a link back to src/. In
# the image the package is a wheel and this path leads nowhere, so the image sets
# WEB_DIR.
SOURCE_TREE_WEB_DIR = Path(__file__).resolve().parents[2] / "web" / "dist"


class PageFiles(StaticFiles):
    """The built page's folder, with a Cache-Control header on every file it sends.

    Vite puts a hash of the content in the name of everything under assets/, so a new
    build is a new name and an old one never changes: those are kept for a year. Every
    other file, index.html above all, keeps its name from one build to the next, so a
    browser may keep it but must ask each time, and the ETag makes that a 304 when
    nothing has changed. Without a header a browser may reuse an old index.html by
    guesswork, and with it the old bundle, long after a deploy.
    """

    ASSETS = "assets"
    ALWAYS_ASK = "no-cache"
    NEVER_CHANGES = "public, max-age=31536000, immutable"

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        # Only a file sent (200) or confirmed unchanged (304): a 404 or a redirect is
        # left as it was. `path` is relative to the folder, with the OS's separator.
        if response.status_code in (200, 304):
            is_asset = Path(path).parts[:1] == (self.ASSETS,)
            response.headers["Cache-Control"] = self.NEVER_CHANGES if is_asset else self.ALWAYS_ASK
        return response


def default_web_dir() -> Path:
    """The folder of the built page: WEB_DIR if it is set, else web/dist in the source tree."""
    from_environment = os.environ.get("WEB_DIR")
    return Path(from_environment) if from_environment else SOURCE_TREE_WEB_DIR


def create_app(
    database_url: str | None = None, web_dir: str | os.PathLike[str] | None = None
) -> FastAPI:
    """Build the app.

    A test passes the URL of its own database, and the folder its page is in, or one
    with no page. Nothing else does: the server takes the database from DATABASE_URL
    and the page from WEB_DIR (see default_web_dir).
    """

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

    folder = Path(web_dir) if web_dir is not None else default_web_dir()
    if (folder / "index.html").is_file():
        # Mounted after the router, on purpose. A Mount at "/" answers every path no
        # route claimed first, and routes are tried in the order they were added, so
        # mounting it first would put the page in front of every endpoint. (/docs and
        # /openapi.json are added when FastAPI is constructed, before any of this, so
        # they would survive the mistake; an endpoint would not.)
        app.mount("/", PageFiles(directory=folder, html=True), name="page")
    else:
        log.info("The page is not built (no index.html in %s), so / redirects to /docs", folder)

        @app.get("/", include_in_schema=False)
        async def front_page() -> RedirectResponse:
            return RedirectResponse(url="/docs")

    return app


app = create_app()
