"""Where the page is mounted: at "/", after every endpoint, and only if it is built.

No database and no network. The app's lifespan is not run, so no pool is made; the one
test that needs an endpoint to answer swaps the connection for a stand-in that finds
no trades (app.dependency_overrides, as the README describes), which still leaves the
real route, the real settlement rules and the real JSON.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from energy_positions.app import SOURCE_TREE_WEB_DIR, create_app, default_web_dir
from energy_positions.db import get_connection

NOWHERE = "postgresql://nobody@127.0.0.1:1/nothing"
PAGE = "<!doctype html><title>the built page</title><p>THE BUILT PAGE</p>"


class NoTrades:
    """Stands in for a connection to a database in which nothing has been traded."""

    async def fetch(self, *_arguments: object) -> list[object]:
        return []


async def no_trades() -> AsyncIterator[NoTrades]:
    yield NoTrades()


@pytest.fixture
def folder_with_a_page(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def no_web_dir_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEB_DIR", raising=False)


def client_of(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_the_root_serves_the_page_when_it_is_built(folder_with_a_page: Path) -> None:
    app = create_app(NOWHERE, web_dir=folder_with_a_page)
    async with client_of(app) as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert response.text == PAGE


async def test_the_docs_still_answer_beside_the_page(folder_with_a_page: Path) -> None:
    app = create_app(NOWHERE, web_dir=folder_with_a_page)
    async with client_of(app) as client:
        docs = await client.get("/docs")
        schema = await client.get("/openapi.json")

    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()
    assert schema.status_code == 200
    assert "/portfolios/{portfolio_id}/positions" in schema.json()["paths"]


async def test_an_endpoint_still_reaches_the_api_and_not_the_page(folder_with_a_page: Path) -> None:
    # The page is mounted at "/", so a path no route has claimed lands on the page. If
    # it were mounted before the router it would claim this one too: the answer would
    # be the page, or a 404 from the page's folder, and never a list of fifty rows.
    # 25 Oct 2026 is the day the clocks go back, so fifty is the API's own answer.
    app = create_app(NOWHERE, web_dir=folder_with_a_page)
    app.dependency_overrides[get_connection] = no_trades
    async with client_of(app) as client:
        response = await client.get("/portfolios/7/positions", params={"settlement_date": "2026-10-25"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    rows = response.json()
    assert len(rows) == 50
    assert rows[0]["settlement_period"]["period"] == 1
    assert rows[0]["net_mwh"] == "0.000"
    assert PAGE not in response.text


async def test_a_post_to_an_endpoint_path_still_reaches_the_api(folder_with_a_page: Path) -> None:
    # An empty body is refused by the API's own validation, which names what is missing.
    # The page's folder would answer a POST with 405, and say nothing about trades.
    app = create_app(NOWHERE, web_dir=folder_with_a_page)
    app.dependency_overrides[get_connection] = no_trades
    async with client_of(app) as client:
        response = await client.post("/trades", json={})

    assert response.status_code == 422
    missing = {error["loc"][-1] for error in response.json()["detail"]}
    assert {"portfolio_id", "period_start", "volume_mwh", "price"} <= missing


async def test_with_no_page_the_root_redirects_to_the_docs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        app = create_app(NOWHERE, web_dir=tmp_path)
    async with client_of(app) as client:
        response = await client.get("/", follow_redirects=False)
        docs = await client.get("/docs")

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
    assert docs.status_code == 200
    said = [record.getMessage() for record in caplog.records if "page is not built" in record.getMessage()]
    assert len(said) == 1
    assert str(tmp_path) in said[0]


async def test_with_no_page_an_endpoint_is_just_as_reachable(tmp_path: Path) -> None:
    app = create_app(NOWHERE, web_dir=tmp_path)
    app.dependency_overrides[get_connection] = no_trades
    async with client_of(app) as client:
        response = await client.get("/portfolios/7/positions", params={"settlement_date": "2026-03-29"})

    assert response.status_code == 200
    assert len(response.json()) == 46


async def test_a_folder_with_no_index_is_no_page(tmp_path: Path) -> None:
    (tmp_path / "something-else.txt").write_text("not a page", encoding="utf-8")
    app = create_app(NOWHERE, web_dir=tmp_path)
    async with client_of(app) as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 307


async def test_web_dir_in_the_environment_says_where_the_page_is(
    folder_with_a_page: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_DIR", str(folder_with_a_page))
    app = create_app(NOWHERE)
    async with client_of(app) as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert response.text == PAGE


async def test_the_argument_beats_the_environment(
    folder_with_a_page: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path_factory.mktemp("empty")
    monkeypatch.setenv("WEB_DIR", str(folder_with_a_page))
    app = create_app(NOWHERE, web_dir=empty)
    async with client_of(app) as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code == 307


def test_with_nothing_said_the_page_is_looked_for_in_web_dist_beside_src() -> None:
    expected = Path(__file__).resolve().parent.parent / "web" / "dist"

    assert default_web_dir() == expected
    assert SOURCE_TREE_WEB_DIR == expected


def test_an_empty_web_dir_is_the_same_as_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # `set WEB_DIR=` in cmd, or an unset variable passed on as an empty string.
    monkeypatch.setenv("WEB_DIR", "")

    assert default_web_dir() == SOURCE_TREE_WEB_DIR
