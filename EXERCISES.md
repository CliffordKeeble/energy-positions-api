# Exercises

Two parts of this repository are unfinished on purpose. Each exercise says what to
run, what to look for, and what "done" looks like. Neither answer is written down
anywhere in the repository.

Both need the database up and seeded, as in the [README](README.md):

```
docker compose up -d --wait
uv sync
uv run python scripts/apply_sql.py sql/schema.sql
uv run python scripts/seed.py
```

The commands are for the Windows command prompt, run from the repository folder.

---

## 1. The index

`GET /portfolios/{id}/positions?settlement_date=...` sums one portfolio's trades
for one day. The statement is `POSITIONS_FOR_SPAN` in
[`src/energy_positions/queries.py`](src/energy_positions/queries.py). The `trades`
table holds about 2.6 million rows and has no index except its primary key.

### What to run

```
uv run python scripts/explain.py before
```

It runs `EXPLAIN (ANALYZE, BUFFERS)` on that statement for portfolio 7 on
15 June 2026, prints three lines, and writes the whole plan to
`out\explain_before_<time>.txt`. Open the file.

### What to look for

- **How `trades` is read.** Find the innermost node of the plan, the one that
  touches the table.
- **`Rows Removed by Filter`.** How many rows did PostgreSQL read in order to keep
  a few dozen?
- **`Buffers`.** Each buffer is an 8 kB page. How much of the table was read?
- **The execution time**, on the last line.
- **The list of indexes on `trades`**, near the top of the file.

Work out, from the `WHERE` clause, what PostgreSQL would need in order to go
straight to the rows it wants.

### What to do

Write the index as a migration, in a new file `sql\migrations\001_<a name>.sql`,
and apply it:

```
uv run python scripts/apply_sql.py sql\migrations\001_<a name>.sql
uv run python scripts/explain.py after
```

Then put `out\explain_before_*.txt` and `out\explain_after_*.txt` side by side.

### What done looks like

- `trades` is no longer read by a `Seq Scan`. An `Index Scan`, an
  `Index Only Scan` or a `Bitmap Heap Scan` has taken its place.
- `Rows Removed by Filter` has gone, or is small.
- The buffer count has fallen from tens of thousands to tens or hundreds.
- The execution time is a small fraction of what it was.
- The top node of the plan may have changed too. That is a consequence, not the
  point: the line to compare is the one that reads `trades`.
- `uv run pytest` gives the same result as before.

The times are from synthetic data on your own machine. They tell you which plan is
cheaper, and by roughly how much, and nothing else.

### Questions worth answering before you call it finished

- Your index names its columns in some order. Does the order matter for this
  query? Try the other order and look at the plan.
- Does the plan still visit the table itself, or is the index enough? What would
  have to be true for the index to be enough?
- `GET /portfolios/{id}/daily` has a similar `WHERE` clause. Does your index help
  it?
- What does the index cost? Ask PostgreSQL how big it is beside the table it
  serves (`pg_relation_size`), and say what has to happen to it on every insert.

---

## 2. The lost update

`POST /trades` stores a trade and keeps a running net for the portfolio and period
in the `positions` table. `GET /portfolios/{id}/positions/current` reads that
running net. The code is `record_a_trade` in
[`src/energy_positions/routes.py`](src/energy_positions/routes.py).

### What to run

One test is expected to fail and is marked so, which is why the suite is green.
Run it with the mark ignored, to see the failure itself:

```
uv run pytest tests/test_lost_update.py --runxfail
```

### What to look for

The test sends one trade of 100 MWh, then twenty trades of 1 MWh at the same
moment, all for one portfolio and one period. Then it asks the API the same
question twice: what do the trades add up to, and what does the position say?

- Read the failure message. The trades add up to 120. What does the position say?
  Run it a few times. Is it the same wrong number each time?
- Every one of the twenty-one requests returned `201 Created`. Nothing raised an
  error. Where did the missing volume go?
- Read `record_a_trade`. Take two requests and write down, statement by statement,
  an order of events in which one of them is lost.
- The two writes are already inside one transaction. Why does that not help? Look
  up what PostgreSQL's default isolation level promises, and what it does not.

### What to do

Repair `POST /trades` so that trades arriving together all reach the position. The
statements are in `queries.py` and the endpoint is in `routes.py`. Leave the test
as it is.

There is more than one sound repair. Some make the database do the adding, in a
single statement. Others make the second request wait until the first has
finished. Either is acceptable here. Know what the other one is, and what each
does when the position row does not exist yet.

### What done looks like

1. Run the whole suite:

   ```
   uv run pytest
   ```

   It now reports the test as **FAILED**, with `[XPASS(strict)]`. That is the mark
   doing its job: the test was expected to fail, it passed, and a strict mark
   treats that as an error so that a stale mark cannot be left behind.

2. Delete the `@pytest.mark.xfail(...)` decorator from
   `tests/test_lost_update.py` and run the suite again. Every test passes and none
   is reported as `xfailed`.

3. Run the test ten times. It passes ten times:

   ```
   for /L %i in (1,1,10) do @uv run pytest tests/test_lost_update.py -q
   ```

### Questions worth answering before you call it finished

- Does your repair still hold when the very first trades for a period arrive
  together, before any position row exists? The test does not cover that. How
  would you test it?
- Would raising the isolation level have fixed it without changing the SQL? What
  would the API then have to do that it does not do now?
- The trades table and the positions table can still be compared at any time.
  Write the query that lists every portfolio and period where they disagree.
