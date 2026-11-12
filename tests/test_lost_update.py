"""Trades that arrive at the same moment. Needs the container: docker compose up -d --wait

This test is expected to fail, and is marked so. It is exercise 2 in EXERCISES.md.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from energy_positions.clock import FixedClock, get_clock
from energy_positions.settlement import SettlementPeriod

pytestmark = pytest.mark.db

PORTFOLIO = 7
PERIOD = SettlementPeriod.from_settlement(date(2026, 11, 12), 20)
AT_ONCE = 20


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="exercise 2: POST /trades loses updates when trades arrive together (see EXERCISES.md)",
)
async def test_trades_that_arrive_together_all_reach_the_position(app: FastAPI, client: AsyncClient) -> None:
    app.dependency_overrides[get_clock] = lambda: FixedClock(PERIOD.start_utc + timedelta(minutes=5))

    async def trade(volume_mwh: str) -> None:
        response = await client.post(
            "/trades",
            json={
                "portfolio_id": PORTFOLIO,
                "period_start": PERIOD.start_utc.isoformat(),
                "volume_mwh": volume_mwh,
                "price": "80.00",
            },
        )
        response.raise_for_status()  # every trade is accepted; that is not what goes wrong

    await trade("100.000")  # an opening trade, on its own, so the position exists
    await asyncio.gather(*(trade("1.000") for _ in range(AT_ONCE)))  # then twenty at once

    # Two answers to one question, from the same API.
    day = await client.get(f"/portfolios/{PORTFOLIO}/positions", params={"settlement_date": "2026-11-12"})
    current = await client.get(f"/portfolios/{PORTFOLIO}/positions/current")
    day.raise_for_status()
    current.raise_for_status()
    summed_from_trades = Decimal(day.json()[PERIOD.number - 1]["net_mwh"])
    running_position = Decimal(current.json()["net_mwh"])

    assert running_position == summed_from_trades, (
        f"the trades for the period add up to {summed_from_trades} MWh "
        f"but the position says {running_position} MWh"
    )
