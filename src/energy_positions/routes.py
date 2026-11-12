"""The endpoints.

Each one is given what it needs by FastAPI: a database connection for the length of
the request, and a clock where it has to know what the time is.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from energy_positions import queries
from energy_positions.clock import Clock, get_clock
from energy_positions.db import get_connection
from energy_positions.models import ZERO_MWH, DailyTotal, Position, Trade, TradeIn
from energy_positions.settlement import SettlementPeriod, periods_in

router = APIRouter()

Connection = Annotated[asyncpg.Connection, Depends(get_connection)]
CurrentClock = Annotated[Clock, Depends(get_clock)]
PortfolioId = Annotated[int, Path(gt=0)]

# The dates the API will answer for. Wide enough for any demo; narrow enough that
# date arithmetic cannot run off the end of the calendar.
EARLIEST, LATEST = date(2000, 1, 1), date(2100, 12, 31)


def _first_instant_of(settlement_date: date):
    return SettlementPeriod.from_settlement(settlement_date, 1).start_utc


@router.get("/portfolios/{portfolio_id}/positions", response_model=list[Position])
async def positions_for_a_settlement_date(
    portfolio_id: PortfolioId,
    settlement_date: Annotated[date, Query(ge=EARLIEST, le=LATEST)],
    connection: Connection,
) -> list[Position]:
    """One row for every settlement period of the date: 48 of them, or 46, or 50.

    The net for each period is summed from the portfolio's trades.
    """
    periods = periods_in(settlement_date)
    rows = await connection.fetch(
        queries.POSITIONS_FOR_SPAN, portfolio_id, periods[0].start_utc, periods[-1].end_utc
    )
    net_by_start = {row["period_start"]: row["net_mwh"] for row in rows}
    return [
        Position(settlement_period=period, net_mwh=net_by_start.get(period.start_utc, ZERO_MWH))
        for period in periods
    ]


@router.get("/portfolios/{portfolio_id}/positions/current", response_model=Position)
async def position_for_the_current_period(
    portfolio_id: PortfolioId, connection: Connection, clock: CurrentClock
) -> Position:
    """The settlement period in progress now, and the portfolio's running net for it.

    "Now" is the injected clock's. The net is read from the positions table, which
    POST /trades keeps up to date.
    """
    period = SettlementPeriod.containing(clock.now())
    net = await connection.fetchval(queries.POSITION_NET, portfolio_id, period.start_utc)
    return Position(settlement_period=period, net_mwh=ZERO_MWH if net is None else net)


@router.get("/portfolios/{portfolio_id}/daily", response_model=list[DailyTotal])
async def daily_totals(
    portfolio_id: PortfolioId,
    from_date: Annotated[date, Query(alias="from", ge=EARLIEST, le=LATEST)],
    to_date: Annotated[date, Query(alias="to", ge=EARLIEST, le=LATEST)],
    connection: Connection,
) -> list[DailyTotal]:
    """Net volume by settlement date, for every date from `from` to `to` that has trades.

    Both ends are settlement dates and both are included.
    """
    if to_date < from_date:
        raise HTTPException(status_code=422, detail="'to' is before 'from'")
    rows = await connection.fetch(
        queries.DAILY_TOTALS_FOR_SPAN,
        portfolio_id,
        _first_instant_of(from_date),
        _first_instant_of(to_date + timedelta(days=1)),
    )
    return [DailyTotal(settlement_date=row["settlement_date"], net_mwh=row["net_mwh"]) for row in rows]


@router.post("/trades", response_model=Trade, status_code=201)
async def record_a_trade(trade: TradeIn, connection: Connection, clock: CurrentClock) -> Trade:
    """Store a trade and bring the portfolio's position for that period up to date.

    Both writes happen in one transaction.
    """
    period = trade.period_start
    traded_at = clock.now()

    async with connection.transaction():
        trade_id = await connection.fetchval(
            queries.INSERT_TRADE, trade.portfolio_id, period.start_utc, trade.volume_mwh, trade.price, traded_at
        )

        # Deliberately naive: read the net, add to it here, write the answer back.
        # It is correct for one request at a time and it is not correct for two.
        # tests/test_lost_update.py shows how, and EXERCISES.md asks for the repair.
        net = await connection.fetchval(queries.POSITION_NET, trade.portfolio_id, period.start_utc)
        if net is None:
            await connection.execute(
                queries.INSERT_POSITION, trade.portfolio_id, period.start_utc, trade.volume_mwh
            )
        else:
            await connection.execute(
                queries.UPDATE_POSITION, trade.portfolio_id, period.start_utc, net + trade.volume_mwh
            )

    return Trade(
        id=trade_id,
        portfolio_id=trade.portfolio_id,
        settlement_period=period,
        volume_mwh=trade.volume_mwh,
        price=trade.price,
        traded_at=traded_at,
    )
