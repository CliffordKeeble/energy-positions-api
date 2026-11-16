"""What the live deployment depends on: Neon's connection string, and the front door.

No database and no network: the URLs below are made up, in the shape Neon's console
hands out.
"""

from __future__ import annotations

from pathlib import Path

from asyncpg import connect_utils
from httpx import ASGITransport, AsyncClient

from energy_positions.app import create_app
from energy_positions.db import DEFAULT_DATABASE_URL, connect_arguments

DIRECT = (
    "postgresql://neondb_owner:Xy7p-q9Rt@ep-quiet-sky-a1b2c3d4.eu-west-2.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
)
POOLED = DIRECT.replace("a1b2c3d4.", "a1b2c3d4-pooler.")


def as_asyncpg_reads_it(dsn: str):
    """asyncpg's own parsing of a DSN, at the version in uv.lock: no connection made."""
    _, parameters = connect_utils._parse_connect_dsn_and_args(
        dsn=dsn, host=None, port=None, user=None, password=None, passfile=None,
        database=None, ssl=None, service=None, servicefile=None, direct_tls=None,
        server_settings=None, target_session_attrs=None, krbsrvname=None, gsslib=None,
    )
    return parameters


def test_asyncpg_would_send_channel_binding_to_the_server_as_a_setting() -> None:
    # The premise of the fix. If a later asyncpg learns channel_binding, this goes red
    # and connect_arguments no longer needs to take it out.
    assert as_asyncpg_reads_it(DIRECT).server_settings == {"channel_binding": "require"}


def test_the_direct_url_loses_channel_binding_and_keeps_tls() -> None:
    dsn, options = connect_arguments(DIRECT)

    assert dsn == DIRECT.replace("&channel_binding=require", "")
    assert options == {}
    parameters = as_asyncpg_reads_it(dsn)
    assert parameters.server_settings is None
    assert parameters.sslmode is connect_utils.SSLMode.require
    assert parameters.database == "neondb"
    assert parameters.password == "Xy7p-q9Rt"


def test_the_pooled_url_also_turns_off_the_prepared_statement_cache() -> None:
    dsn, options = connect_arguments(POOLED)

    assert "channel_binding" not in dsn
    assert options == {"statement_cache_size": 0}


def test_the_local_url_is_handed_over_unchanged() -> None:
    assert connect_arguments(DEFAULT_DATABASE_URL) == (DEFAULT_DATABASE_URL, {})


async def test_the_root_sends_a_visitor_to_the_docs(tmp_path: Path) -> None:
    # The app's lifespan is not run here, so no database is needed or reached.
    # The page folder is an empty one this test names, so it does not depend on whether
    # this machine has built web/dist or set WEB_DIR.
    app = create_app("postgresql://nobody@127.0.0.1:1/nothing", web_dir=tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
