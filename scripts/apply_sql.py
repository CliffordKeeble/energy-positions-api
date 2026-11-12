"""Apply SQL files to the database, in the order given.

    uv run python scripts/apply_sql.py sql/schema.sql

The database is DATABASE_URL, or the one in compose.yaml if that is not set.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import asyncpg

from energy_positions.db import database_url, describe


async def apply(paths: list[Path]) -> None:
    url = database_url()
    connection = await asyncpg.connect(url)
    try:
        for path in paths:
            started = time.perf_counter()
            await connection.execute(path.read_text(encoding="utf-8"))
            print(f"applied {path} to {describe(url)} in {time.perf_counter() - started:.1f} s")
    finally:
        await connection.close()


def main() -> int:
    paths = [Path(argument) for argument in sys.argv[1:]]
    if not paths:
        print("usage: apply_sql.py <file.sql> [<file.sql> ...]", file=sys.stderr)
        return 2
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        print(f"no such file: {', '.join(missing)}", file=sys.stderr)
        return 2
    asyncio.run(apply(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
