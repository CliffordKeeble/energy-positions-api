"""Every SQL statement the API runs, in one place and in full.

There is no ORM. The statements are plain strings so that what PostgreSQL is asked
to do can be read here, pasted into psql, and put in front of EXPLAIN.

Parameters are asyncpg's: $1, $2, ... Every instant passed in is an aware UTC
datetime and every column that holds one is timestamptz.
"""

# One portfolio's net volume for each settlement period in a span of instants,
# summed from its trades. Periods with no trades have no row; the API fills those in.
#   $1 portfolio id   $2 first instant, inclusive   $3 last instant, exclusive
POSITIONS_FOR_SPAN = """
SELECT period_start,
       sum(volume_mwh) AS net_mwh
FROM trades
WHERE portfolio_id = $1
  AND period_start >= $2
  AND period_start < $3
GROUP BY period_start
ORDER BY period_start
"""

# One portfolio's net volume for each settlement date in a span of instants.
#
# The settlement date is the UK local day, so the instant is moved to Europe/London
# before the date is taken. Taking the date in UTC instead looks the same all winter
# and is wrong all summer: from late March to late October the first two periods of
# every settlement date start before midnight UTC, and would be counted in the day
# before.
#   $1 portfolio id   $2 first instant, inclusive   $3 last instant, exclusive
DAILY_TOTALS_FOR_SPAN = """
SELECT (period_start AT TIME ZONE 'Europe/London')::date AS settlement_date,
       sum(volume_mwh) AS net_mwh
FROM trades
WHERE portfolio_id = $1
  AND period_start >= $2
  AND period_start < $3
GROUP BY (period_start AT TIME ZONE 'Europe/London')::date
ORDER BY settlement_date
"""

# The running net for one portfolio and period, or no row if it has never traded.
#   $1 portfolio id   $2 period start
POSITION_NET = """
SELECT net_mwh
FROM positions
WHERE portfolio_id = $1
  AND period_start = $2
"""

#   $1 portfolio id   $2 period start   $3 volume   $4 price   $5 traded at
INSERT_TRADE = """
INSERT INTO trades (portfolio_id, period_start, volume_mwh, price, traded_at)
VALUES ($1, $2, $3, $4, $5)
RETURNING id
"""

#   $1 portfolio id   $2 period start   $3 net
INSERT_POSITION = """
INSERT INTO positions (portfolio_id, period_start, net_mwh)
VALUES ($1, $2, $3)
"""

#   $1 portfolio id   $2 period start   $3 net
UPDATE_POSITION = """
UPDATE positions
SET net_mwh = $3
WHERE portfolio_id = $1
  AND period_start = $2
"""
