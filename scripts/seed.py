"""Fill the database with synthetic trades.

    uv run python scripts/seed.py

Everything it writes is made up by a random number generator with a fixed seed: the
volumes, the prices and the times. None of it is real data, and running it twice
gives the same rows. It empties the trades and positions tables first.

50 portfolios trade in every settlement period of 2025 and 2026, between no times
and three times a period. That comes to about 2.6 million trades, which is enough
for a query with no index to be visibly slow.
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import asyncpg

from energy_positions.db import database_url, describe
from energy_positions.settlement import periods_in

SEED = 20261112
PORTFOLIO_IDS = range(1, 51)
FIRST_DATE, LAST_DATE = date(2025, 1, 1), date(2026, 12, 31)
TRADES_IN_A_PERIOD = (0, 1, 1, 2, 2, 3)  # drawn from evenly: 1.5 on average

Row = tuple[int, datetime, Decimal, Decimal, datetime]
COLUMNS = ["portfolio_id", "period_start", "volume_mwh", "price", "traded_at"]


def trades_on(settlement_date: date, rng: random.Random) -> Iterator[Row]:
    """The day's trades, period by period, so that rows arrive roughly in time order."""
    for period in periods_in(settlement_date):
        for portfolio_id in PORTFOLIO_IDS:
            for _ in range(rng.choice(TRADES_IN_A_PERIOD)):
                yield (
                    portfolio_id,
                    period.start_utc,
                    Decimal(rng.randint(-50_000, 50_000)).scaleb(-3),  # -50.000 to 50.000 MWh
                    Decimal(rng.randint(2_000, 15_000)).scaleb(-2),  # 20.00 to 150.00 per MWh
                    period.start_utc - timedelta(minutes=rng.randint(60, 7 * 24 * 60)),
                )


def months(first: date, last: date) -> Iterator[list[date]]:
    """The dates from first to last, a calendar month at a time."""
    month: list[date] = []
    day = first
    while day <= last:
        if month and day.month != month[-1].month:
            yield month
            month = []
        month.append(day)
        day += timedelta(days=1)
    yield month


async def seed() -> None:
    url = database_url()
    rng = random.Random(SEED)
    started = time.perf_counter()
    connection = await asyncpg.connect(url)
    try:
        print(f"seeding {describe(url)} with synthetic trades (random seed {SEED})")
        await connection.execute("TRUNCATE trades, positions RESTART IDENTITY")

        total = 0
        for month in months(FIRST_DATE, LAST_DATE):
            rows = [row for day in month for row in trades_on(day, rng)]
            await connection.copy_records_to_table("trades", records=rows, columns=COLUMNS)
            total += len(rows)
            print(f"  {month[0]:%Y-%m}: {len(rows):>9,} trades   {total:>10,} so far")
        loaded = time.perf_counter()

        # The positions table starts out agreeing with the trades.
        await connection.execute(
            """
            INSERT INTO positions (portfolio_id, period_start, net_mwh)
            SELECT portfolio_id, period_start, sum(volume_mwh)
            FROM trades
            GROUP BY portfolio_id, period_start
            """
        )
        # Fresh statistics and a visibility map, so that a query plan depends on the
        # schema and the query and not on whether autovacuum has been round yet.
        await connection.execute("VACUUM (ANALYZE) trades")
        await connection.execute("VACUUM (ANALYZE) positions")
        finished = time.perf_counter()

        trades = await connection.fetchval("SELECT count(*) FROM trades")
        positions = await connection.fetchval("SELECT count(*) FROM positions")
    finally:
        await connection.close()

    print(f"trades:    {trades:,} rows")
    print(f"positions: {positions:,} rows")
    print(
        f"seeded in {finished - started:.1f} s "
        f"({loaded - started:.1f} s loading trades, "
        f"{finished - loaded:.1f} s filling positions and analysing)"
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(seed()))
