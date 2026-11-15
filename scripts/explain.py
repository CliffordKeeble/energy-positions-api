"""Ask PostgreSQL how it runs the positions query, and keep the answer.

    uv run python scripts/explain.py before

Runs EXPLAIN (ANALYZE, BUFFERS) on the query behind
GET /portfolios/{id}/positions?settlement_date=..., for one fixed portfolio and
settlement date, and writes the plan to out/explain_<label>_<London time>.txt.
The label is yours: it only names the file, so that two runs can be told apart.

The query is run once first and that run is thrown away, so the plan that is kept
was measured with the data already in memory. Without that, the first run of the
day reads from disk and looks slower than the query is.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from energy_positions import queries
from energy_positions.clock import SystemClock
from energy_positions.db import connect, database_url, describe
from energy_positions.settlement import LONDON, periods_in

PORTFOLIO_ID = 7
SETTLEMENT_DATE = date(2026, 6, 15)

REPOSITORY = Path(__file__).resolve().parent.parent
OUT = REPOSITORY / "out"


def node_name(plan_line: str) -> str:
    """'  ->  Seq Scan on trades  (cost=...)' becomes 'Seq Scan on trades'."""
    return re.sub(r"\s+\(cost=.*$", "", plan_line).replace("->", "").strip()


def commit() -> str:
    """The commit the working tree is at, so the file says what produced it."""
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPOSITORY, capture_output=True, text=True, check=True
        ).stdout.strip()
        changed = subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPOSITORY, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown (not a git checkout)"
    return f"{revision}, plus uncommitted changes" if changed else revision


async def explain(label: str) -> None:
    url = database_url()
    periods = periods_in(SETTLEMENT_DATE)
    parameters = (PORTFOLIO_ID, periods[0].start_utc, periods[-1].end_utc)

    connection = await connect(url)
    try:
        await connection.fetch(queries.POSITIONS_FOR_SPAN, *parameters)  # warm up; not measured
        rows = await connection.fetch(
            "EXPLAIN (ANALYZE, BUFFERS) " + queries.POSITIONS_FOR_SPAN, *parameters
        )
        indexes = await connection.fetch(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = current_schema() AND tablename = 'trades' ORDER BY indexname"
        )
        trade_count = await connection.fetchval("SELECT count(*) FROM trades")
        server = await connection.fetchval("SHOW server_version")
    finally:
        await connection.close()

    plan = [row[0] for row in rows]
    top_node = node_name(plan[0])
    scans = [node_name(line) for line in plan if re.search(r"\bScan\b.*\(cost=", line)]
    execution_time = next(line for line in plan if line.startswith("Execution Time"))

    now = SystemClock().now().astimezone(LONDON)
    report = [
        f"label:              {label}",
        f"written:            {now:%Y-%m-%d %H:%M:%S %Z} (Europe/London)",
        f"commit:             {commit()}",
        f"database:           {describe(url)}, PostgreSQL {server}",
        f"trades:             {trade_count:,} rows",
        "indexes on trades:",
        *(f"    {index['indexdef']}" for index in indexes),
        "",
        f"query:              positions for portfolio {PORTFOLIO_ID} on settlement date "
        f"{SETTLEMENT_DATE.isoformat()} ({len(periods)} periods)",
        *(f"    {line}" for line in queries.POSITIONS_FOR_SPAN.strip().splitlines()),
        f"    $1 = {parameters[0]}, $2 = {parameters[1].isoformat()}, $3 = {parameters[2].isoformat()}",
        "",
        f"top node:           {top_node}",
        f"how trades is read: {'; '.join(scans)}",
        f"{execution_time.replace('Execution Time:', 'execution time:    ')}",
        "    measured after one warm-up run, on synthetic data, on one machine",
        "",
        "plan:",
        *(f"    {line}" for line in plan),
        "",
    ]

    OUT.mkdir(exist_ok=True)
    path = OUT / f"explain_{label}_{now:%Y%m%d_%H%M%S}.txt"
    path.write_text("\n".join(report), encoding="utf-8", newline="\n")

    print(f"top node:           {top_node}")
    print(f"how trades is read: {'; '.join(scans)}")
    print(execution_time.replace("Execution Time:", "execution time:    "))
    print(f"plan written to {path.relative_to(REPOSITORY)}")


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", sys.argv[1]):
        print("usage: explain.py <label>    (letters, digits, - and _ only)", file=sys.stderr)
        return 2
    asyncio.run(explain(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
