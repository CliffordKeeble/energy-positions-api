"""The endpoints, against PostgreSQL. Needs the container: docker compose up -d --wait"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from conftest import add_trade
from energy_positions.clock import FixedClock, get_clock
from energy_positions.settlement import LONDON, SettlementPeriod

pytestmark = pytest.mark.db

SPRING = date(2026, 3, 29)  # clocks go forward: 46 periods
AUTUMN = date(2026, 10, 25)  # clocks go back: 50 periods
ORDINARY = date(2026, 11, 12)
SUMMER = date(2026, 6, 15)  # a day on BST: it starts at 23:00 UTC the evening before

PORTFOLIO = 7


def set_the_clock(app: FastAPI, instant: datetime) -> None:
    app.dependency_overrides[get_clock] = lambda: FixedClock(instant)


# --- GET /portfolios/{id}/positions/current ---------------------------------------


@pytest.mark.parametrize(
    ("now", "expected_period", "expected_start"),
    [
        (datetime(2026, 10, 25, 0, 15, tzinfo=UTC), 3, "2026-10-25T00:00:00Z"),
        (datetime(2026, 10, 25, 1, 15, tzinfo=UTC), 5, "2026-10-25T01:00:00Z"),
    ],
    ids=["01:15-BST", "01:15-GMT"],
)
async def test_the_current_period_in_the_repeated_hour(
    app: FastAPI, client: AsyncClient, now: datetime, expected_period: int, expected_start: str
) -> None:
    # Both instants read 01:15 on a UK clock. They are an hour apart.
    assert (now.astimezone(LONDON).hour, now.astimezone(LONDON).minute) == (1, 15)
    set_the_clock(app, now)

    response = await client.get(f"/portfolios/{PORTFOLIO}/positions/current")

    assert response.status_code == 200
    assert response.json() == {
        "settlement_period": {
            "settlement_date": "2026-10-25",
            "period": expected_period,
            "start_utc": expected_start,
        },
        "net_mwh": "0.000",
    }


async def test_the_current_position_is_the_running_net_for_the_period(
    app: FastAPI, client: AsyncClient
) -> None:
    period = SettlementPeriod.from_settlement(ORDINARY, 20)
    set_the_clock(app, period.start_utc.replace(minute=period.start_utc.minute + 10))
    for volume in ("10.000", "-2.500"):
        response = await client.post(
            "/trades",
            json={
                "portfolio_id": PORTFOLIO,
                "period_start": period.start_utc.isoformat(),
                "volume_mwh": volume,
                "price": "80.00",
            },
        )
        assert response.status_code == 201

    current = (await client.get(f"/portfolios/{PORTFOLIO}/positions/current")).json()
    other_portfolio = (await client.get(f"/portfolios/{PORTFOLIO + 1}/positions/current")).json()

    assert current["settlement_period"]["period"] == 20
    assert current["net_mwh"] == "7.500"
    assert other_portfolio["net_mwh"] == "0.000"


# --- GET /portfolios/{id}/positions?settlement_date= -------------------------------


@pytest.mark.parametrize(
    ("settlement_date", "expected"),
    [(SPRING, 46), (AUTUMN, 50), (ORDINARY, 48)],
    ids=["clocks-forward", "clocks-back", "ordinary"],
)
async def test_positions_has_one_row_for_every_period_of_the_day(
    client: AsyncClient, settlement_date: date, expected: int
) -> None:
    response = await client.get(
        f"/portfolios/{PORTFOLIO}/positions", params={"settlement_date": settlement_date.isoformat()}
    )

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == expected
    assert [row["settlement_period"]["period"] for row in rows] == list(range(1, expected + 1))
    assert {row["settlement_period"]["settlement_date"] for row in rows} == {settlement_date.isoformat()}


async def test_positions_keeps_the_two_one_o_clocks_apart(
    client: AsyncClient, database: asyncpg.Connection
) -> None:
    # Periods 3 and 5 of the autumn day both start at 01:00 on a UK clock.
    await add_trade(database, PORTFOLIO, SettlementPeriod.from_settlement(AUTUMN, 3), "10.000")
    await add_trade(database, PORTFOLIO, SettlementPeriod.from_settlement(AUTUMN, 3), "5.500")
    await add_trade(database, PORTFOLIO, SettlementPeriod.from_settlement(AUTUMN, 5), "-4.000")
    await add_trade(database, PORTFOLIO + 1, SettlementPeriod.from_settlement(AUTUMN, 5), "99.000")
    # The day after's first period is not this day's fifty-first.
    await add_trade(database, PORTFOLIO, SettlementPeriod.from_settlement(AUTUMN, 50).next(), "77.000")

    response = await client.get(f"/portfolios/{PORTFOLIO}/positions", params={"settlement_date": "2026-10-25"})

    net = {row["settlement_period"]["period"]: row["net_mwh"] for row in response.json()}
    assert net[3] == "15.500"
    assert net[5] == "-4.000"
    assert {period: figure for period, figure in net.items() if period not in (3, 5)} == {
        period: "0.000" for period in range(1, 51) if period not in (3, 5)
    }


# --- GET /portfolios/{id}/daily?from=&to= ------------------------------------------


async def test_daily_totals_follow_the_uk_day_not_the_utc_day(
    client: AsyncClient, database: asyncpg.Connection
) -> None:
    # On BST a settlement date starts at 23:00 UTC the evening before, so its first
    # two periods fall on the previous date in UTC. Grouping by the UTC date would
    # move them into the wrong day.
    first, second, last = (SettlementPeriod.from_settlement(SUMMER, n) for n in (1, 2, 48))
    assert first.start_utc == datetime(2026, 6, 14, 23, 0, tzinfo=UTC)
    await add_trade(database, PORTFOLIO, first, "10.000")
    await add_trade(database, PORTFOLIO, second, "20.000")
    await add_trade(database, PORTFOLIO, last, "1.000")
    await add_trade(database, PORTFOLIO, last.next(), "400.000")  # period 1 of 16 June
    await add_trade(database, PORTFOLIO + 1, first, "5000.000")  # someone else's

    response = await client.get(
        f"/portfolios/{PORTFOLIO}/daily", params={"from": "2026-06-15", "to": "2026-06-16"}
    )

    assert response.status_code == 200
    assert response.json() == [
        {"settlement_date": "2026-06-15", "net_mwh": "31.000"},
        {"settlement_date": "2026-06-16", "net_mwh": "400.000"},
    ]


async def test_daily_totals_include_both_ends_and_nothing_outside(
    client: AsyncClient, database: asyncpg.Connection
) -> None:
    for day, volume in [(14, "1.000"), (15, "2.000"), (16, "4.000"), (17, "8.000")]:
        await add_trade(database, PORTFOLIO, SettlementPeriod.from_settlement(date(2026, 6, day), 1), volume)

    response = await client.get(
        f"/portfolios/{PORTFOLIO}/daily", params={"from": "2026-06-15", "to": "2026-06-16"}
    )

    assert response.json() == [
        {"settlement_date": "2026-06-15", "net_mwh": "2.000"},
        {"settlement_date": "2026-06-16", "net_mwh": "4.000"},
    ]


async def test_daily_refuses_a_range_that_ends_before_it_starts(client: AsyncClient) -> None:
    response = await client.get(
        f"/portfolios/{PORTFOLIO}/daily", params={"from": "2026-06-16", "to": "2026-06-15"}
    )

    assert response.status_code == 422


# --- POST /trades ------------------------------------------------------------------


async def test_a_trade_is_stored_and_shows_in_the_positions(
    app: FastAPI, client: AsyncClient, database: asyncpg.Connection
) -> None:
    traded_at = datetime(2026, 10, 24, 9, 30, tzinfo=UTC)
    set_the_clock(app, traded_at)

    response = await client.post(
        "/trades",
        json={
            "portfolio_id": PORTFOLIO,
            "period_start": "2026-10-25T01:00:00Z",
            "volume_mwh": "12.500",
            "price": "84.20",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "portfolio_id": PORTFOLIO,
        "settlement_period": {"settlement_date": "2026-10-25", "period": 5, "start_utc": "2026-10-25T01:00:00Z"},
        "volume_mwh": "12.500",
        "price": "84.20",
        "traded_at": "2026-10-24T09:30:00Z",
    }
    stored = await database.fetchrow("SELECT * FROM trades")
    assert stored["period_start"] == datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    assert stored["volume_mwh"] == Decimal("12.500")
    assert stored["traded_at"] == traded_at
    day = await client.get(f"/portfolios/{PORTFOLIO}/positions", params={"settlement_date": "2026-10-25"})
    assert day.json()[4]["net_mwh"] == "12.500"


async def test_trades_one_after_another_add_up(client: AsyncClient, database: asyncpg.Connection) -> None:
    for volume in ("10.000", "-3.250", "0.750"):
        response = await client.post(
            "/trades",
            json={
                "portfolio_id": PORTFOLIO,
                "period_start": "2026-11-12T09:30:00Z",
                "volume_mwh": volume,
                "price": "80.00",
            },
        )
        assert response.status_code == 201

    assert await database.fetchval("SELECT net_mwh FROM positions") == Decimal("7.500")


@pytest.mark.parametrize(
    "period_start",
    ["2026-11-12T09:30:00", "2026-11-12T09:45:00Z"],
    ids=["no-time-zone", "off-the-half-hour"],
)
async def test_a_trade_for_something_that_is_not_a_period_is_refused(
    client: AsyncClient, database: asyncpg.Connection, period_start: str
) -> None:
    response = await client.post(
        "/trades",
        json={"portfolio_id": PORTFOLIO, "period_start": period_start, "volume_mwh": "1.000", "price": "80.00"},
    )

    assert response.status_code == 422
    assert await database.fetchval("SELECT count(*) FROM trades") == 0
