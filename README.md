# energy-positions-api

[![ci](https://github.com/CliffordKeeble/energy-positions-api/actions/workflows/ci.yml/badge.svg)](https://github.com/CliffordKeeble/energy-positions-api/actions/workflows/ci.yml)

A small API that answers one question: what is a portfolio's net energy position in
each half-hour settlement period of a day in Great Britain?

It is a demo, built to show three things working together:

- **an ASGI API layer**: FastAPI on Uvicorn, with its dependencies injected;
- **PostgreSQL underneath it**, reached with asyncpg and plain SQL, so that the
  queries can be read, explained and tuned;
- **time handled properly**: a settlement day in Great Britain has 48 half-hours,
  except on the two days a year when it has 46 or 50.

All the data is synthetic. It comes from a random number generator with a fixed seed.

## Two things are unfinished on purpose

This repository is also a pair of exercises, written up in [EXERCISES.md](EXERCISES.md).

1. **The `trades` table has no index** beyond its primary key, so the main query
   reads the whole table. The exercise is to read the query plan, add the index, and
   measure the difference.
2. **`POST /trades` loses updates when two trades arrive together.** It reads a
   figure, adds to it in Python and writes it back. A test demonstrates the fault
   and is marked as an expected failure. The exercise is to repair the endpoint.

Neither answer is in the repository.

## Run it

You need [uv](https://docs.astral.sh/uv/) and Docker Desktop. The commands below
are written for the Windows command prompt (cmd), run from the repository folder.

Start PostgreSQL 17. It listens on port 55432 of this machine only, so it cannot
clash with a PostgreSQL that is already installed:

```
docker compose up -d --wait
```

Install Python and the dependencies. uv reads the Python version from
`.python-version` and fetches it if it is not there. The version is pinned to 3.14
because, when this was written, some of the dependencies had no Windows wheels for
3.15 yet:

```
uv sync
```

Create the tables, then fill them. The seed writes about 2.6 million synthetic
trades and takes about a minute on one laptop:

```
uv run python scripts/apply_sql.py sql/schema.sql
uv run python scripts/seed.py
```

Start the API. The port is 8048 and not Uvicorn's default of 8000, because 8000 is
often taken already; on the machine this was written on, a Windows service holds it:

```
uv run uvicorn energy_positions.app:app --port 8048
```

Then open <http://127.0.0.1:8048/docs> for the OpenAPI page, where every endpoint
can be tried. Or, from a second command prompt:

```
curl "http://127.0.0.1:8048/portfolios/7/positions?settlement_date=2026-10-25"
curl "http://127.0.0.1:8048/portfolios/7/positions/current"
curl "http://127.0.0.1:8048/portfolios/7/daily?from=2026-10-24&to=2026-10-26"
curl -X POST http://127.0.0.1:8048/trades -H "Content-Type: application/json" -d "{\"portfolio_id\": 7, \"period_start\": \"2026-10-25T01:00:00Z\", \"volume_mwh\": \"12.500\", \"price\": \"84.20\"}"
```

Stop the API with Ctrl+C. Stop PostgreSQL, keeping its data, with
`docker compose down`. Add `-v` to throw the data away as well.

The addresses say `127.0.0.1` and not `localhost` for a reason. On Windows
`localhost` is tried over IPv6 first, the container is published on IPv4 only, and
each new database connection then waits about two seconds for the miss.

## Run the tests

```
uv run pytest
```

That runs everything and needs the PostgreSQL container. The expected result is
that every test passes except one, which is reported as `xfailed`: that one is
exercise 2.

The tests of the settlement-period rules need no database and no Docker:

```
uv run pytest -m "not db"
```

The database tests use a database of their own, `positions_test`, which they create
on the same server. They never touch the seeded data, so they give the same result
whether or not the seed has been run.

The same suite runs on GitHub for every pull request and every push to `main`
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)), against PostgreSQL 17 in
a service container. The badge at the top is its latest result on `main`.

## Run it live

**Live address:** _not deployed yet_ (`https://<app>.<environment>.uksouth.azurecontainerapps.io`)

### What runs where

- **The API** runs on Azure Container Apps, consumption plan: at least 0 replicas and
  at most 1, each with 0.25 vCPU and 0.5 GiB. With no traffic it scales to nothing.
- **The image** is built and published by CI on every push to `main`, after the
  tests pass: `ghcr.io/cliffordkeeble/energy-positions-api`, tagged with the commit
  and with `latest`. Azure pulls it with no credentials, which works only while the
  package is public: after the first publish, open it from the repository's
  Packages, and if it says Private, change its visibility to Public.
- **The database** is PostgreSQL on Neon's free plan, which also scales to nothing
  when idle.

Both sleep when nobody is using them, so **the first request after a quiet spell can
take up to 30 seconds** while they wake. Locally the container answers in under
3 seconds; the rest is margin for fetching the image and waking the database.

### Why it costs nothing

- **Container Apps** gives each subscription 180,000 vCPU-seconds, 360,000
  GiB-seconds and 2 million requests a month free
  ([billing](https://learn.microsoft.com/azure/container-apps/billing)). At 0.25 vCPU
  and 0.5 GiB, either allowance is 200 hours of a running replica, and with a minimum
  of 0 replicas it runs only while it is being used.
- **Neon's free plan** gives 100 compute-hours and 1 GB of storage per project a
  month ([pricing](https://neon.com/pricing)). The full seed is 386 MB, tables and
  indexes together, measured on the local database.
- **No Log Analytics workspace**, so nothing bills for logs.

### The database on Neon

Create a project in AWS Europe West 2 (London), near Azure's UK South. In the
console's connection details, **turn connection pooling off and copy the direct
URL**: its host has no `-pooler` in it. The app keeps its own pool of connections,
at most ten, from a single replica, so Neon's PgBouncer would add nothing, and in
its transaction mode asyncpg cannot keep prepared statements. Paste the URL as the
console gives it, with `sslmode=require` and `channel_binding=require` on the end:
asyncpg keeps the first, and the app removes the second, which only libpq
understands (see `connect_arguments` in
[`src/energy_positions/db.py`](src/energy_positions/db.py)). If the pooled URL is
used anyway, the app turns asyncpg's statement cache off for it.

Seed it from this folder. The quotes around the `set` matter: the URL contains `&`,
which cmd would otherwise take as the end of the command:

```
set "DATABASE_URL=postgresql://<role>:<password>@ep-<name>.eu-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
```

```
uv run python scripts/apply_sql.py sql/schema.sql
```

```
uv run python scripts/seed.py
```

The seed sends 2.6 million rows over the internet, so it takes longer than it does
locally.

### The Azure commands

None of these has been run. They need the [Azure CLI](https://learn.microsoft.com/cli/azure/)
and an Azure subscription. Sign in, and add the Container Apps commands:

```
az login
```

```
az extension add --name containerapp --upgrade
```

```
az provider register --namespace Microsoft.App
```

A resource group in UK South:

```
az group create --name rg-energy-positions --location uksouth
```

A Container Apps environment with no Log Analytics workspace:

```
az containerapp env create --name cae-energy-positions --resource-group rg-energy-positions --location uksouth --logs-destination none
```

The app, from the public image, with external ingress on the container's port 8000.
The Neon URL is held as a secret, and `DATABASE_URL` refers to the secret rather
than holding the URL itself:

```
az containerapp create --name energy-positions-api --resource-group rg-energy-positions --environment cae-energy-positions --image ghcr.io/cliffordkeeble/energy-positions-api:latest --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi --secrets "database-url=<the direct Neon URL>" --env-vars DATABASE_URL=secretref:database-url
```

Its address, for the line at the top of this section:

```
az containerapp show --name energy-positions-api --resource-group rg-energy-positions --query properties.configuration.ingress.fqdn --output tsv
```

A new image is not picked up by itself. To run a later commit, point the app at
that commit's tag:

```
az containerapp update --name energy-positions-api --resource-group rg-energy-positions --image ghcr.io/cliffordkeeble/energy-positions-api:<commit sha>
```

## Settlement periods

Electricity in Great Britain is traded and settled in half-hours. Each one is a
**settlement period**, and it has two faces.

- **Its identity is the instant it starts, in UTC.** That is what the database
  stores, in a `timestamptz` column, and what the code compares, sorts and hashes.
- **Its business label is (settlement date, period number).** The settlement date
  is the UK local calendar day, and period 1 starts at local midnight.

The label follows the UK clock and the identity does not, and that is the whole
difficulty:

| Settlement date | What happens | Periods |
|---|---|---|
| most days | nothing | 48 |
| the last Sunday of March | the clocks go forward: 01:00 to 02:00 never happens | 46 |
| the last Sunday of October | the clocks go back: 01:00 to 02:00 happens twice | 50 |

On the October day, periods 3 and 5 both start at 01:00 on a UK clock, and periods
4 and 6 both start at 01:30. A local time cannot say which is meant. The UTC
instant can, which is why it is the identity and the label is derived from it.
`GET /portfolios/{id}/positions?settlement_date=2026-10-25` returns 50 rows, and
each row carries both faces:

```json
{
  "settlement_period": {
    "settlement_date": "2026-10-25",
    "period": 5,
    "start_utc": "2026-10-25T01:00:00Z"
  },
  "net_mwh": "0.000"
}
```

The rules live in one module,
[`src/energy_positions/settlement.py`](src/energy_positions/settlement.py), as an
immutable value type. It converts through the `Europe/London` entry of the time
zone database and never through a fixed offset, and it refuses a datetime with no
time zone and an instant that is not on the hour or the half-hour.

### The grouping bug the daily test guards

`GET /portfolios/{id}/daily` totals a portfolio's volume by settlement date. The
SQL has to turn an instant into a date, and there is a wrong way that looks right:

```sql
GROUP BY period_start::date                               -- the session's time zone: UTC here
GROUP BY (period_start AT TIME ZONE 'UTC')::date          -- the same thing, said aloud
GROUP BY (period_start AT TIME ZONE 'Europe/London')::date  -- the settlement date
```

In winter the UK is on UTC and all three agree. From late March to late October a
settlement date starts at 23:00 UTC the evening before, so the first two versions
put the first two periods of every day into the day before. Nothing fails, the
totals are plausible, and every summer day is wrong by an hour of trading. The
query uses the third version, and `test_daily_totals_follow_the_uk_day_not_the_utc_day`
puts trades in that first hour of a June day to keep it there.

## How it is put together

| Layer | Here | The .NET equivalent |
|---|---|---|
| Web server | Uvicorn | Kestrel |
| Web framework | FastAPI | ASP.NET Core minimal APIs |
| Dependency injection | `Depends(...)` in an endpoint's parameters | constructor injection |
| One object for the app's lifetime | the pool, made in `lifespan` and kept on `app.state` | a singleton registration |
| One object per request | a `Depends` whose function has a `yield`: the connection | a scoped lifetime |
| Swapping a dependency in a test | `app.dependency_overrides` | replacing a registration in `WebApplicationFactory` |
| Data shapes and JSON | Pydantic models | records and System.Text.Json |
| PostgreSQL driver | asyncpg | Npgsql |
| Tests | pytest | xUnit |
| Time zones | `zoneinfo` | `TimeZoneInfo`, or NodaTime's `DateTimeZone` |

Where to find each piece:

```
src/energy_positions/
    settlement.py   the settlement period: a pure value type, no clock, no database
    clock.py        time as a service: Clock, SystemClock, FixedClock
    app.py          the app, and the lifespan that owns the connection pool
    db.py           the database URL as asyncpg needs it, and the per-request connection
    routes.py       the four endpoints
    queries.py      every SQL statement, in full
    models.py       the request and response shapes
sql/
    schema.sql      the two tables
    migrations/     empty: exercise 1 puts a file here
scripts/
    apply_sql.py    applies SQL files to the database
    seed.py         synthetic trades, fixed random seed
    explain.py      EXPLAIN (ANALYZE, BUFFERS) of the positions query, written to out/
tests/
    test_settlement.py, test_clock.py    pure
    test_going_live.py                   pure: Neon's URL, and the redirect from /
    test_api.py, test_lost_update.py     marked db: they need the container
Dockerfile          the image: the locked dependencies and the package, run as a non-root user
.github/workflows/  ci.yml: the tests, then the image published to ghcr.io
```

Three choices worth knowing about:

- **No ORM.** The SQL is written out so that the statement PostgreSQL runs is the
  statement you read, and the one you hand to `EXPLAIN`.
- **Time is injected.** Nothing calls `datetime.now()` except `SystemClock`. An
  endpoint that needs the time is given a clock, and a test gives it a `FixedClock`
  set inside the repeated hour of 25 October, where 01:15 on a UK clock is two
  different settlement periods an hour apart.
- **Volumes and prices are decimals from the database to the JSON**, where they are
  written as strings. No figure passes through a binary float.

## What this is not

- **Not a benchmark.** Any timing you see here was taken on synthetic data, on one
  laptop. It says which of two query plans is cheaper and nothing more.
- **Not production code.** There is no authentication, no portfolio table, no
  migration tool, and no configuration beyond `DATABASE_URL`, plus `PORT` for the
  container. The database password in `compose.yaml` is a throwaway for a container
  that only this machine can reach.
- **Not real data.** No trade, price or portfolio here describes anything that
  happened.
