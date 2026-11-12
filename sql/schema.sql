-- The demo's two tables. Applied by scripts/apply_sql.py, never by the app at start-up.
--
-- Every instant is timestamptz, never timestamp. A settlement period is identified by
-- the instant it starts, and a timestamp without a time zone cannot tell apart the two
-- periods that start at 01:00 on the day the clocks go back.
--
-- trades has no index beyond its primary key. That is deliberate: see EXERCISES.md.

CREATE TABLE IF NOT EXISTS trades (
    id            bigserial      PRIMARY KEY,
    portfolio_id  integer        NOT NULL,
    period_start  timestamptz    NOT NULL,  -- the settlement period, by the instant it starts
    volume_mwh    numeric(12, 3) NOT NULL,  -- positive is bought, negative is sold
    price         numeric(10, 2) NOT NULL,  -- per MWh
    traded_at     timestamptz    NOT NULL
);

-- The running net for each portfolio and period, kept up to date by POST /trades.
CREATE TABLE IF NOT EXISTS positions (
    portfolio_id  integer        NOT NULL,
    period_start  timestamptz    NOT NULL,
    net_mwh       numeric(12, 3) NOT NULL,
    PRIMARY KEY (portfolio_id, period_start)
);
