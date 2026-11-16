// The shapes the API sends, as src/energy_positions/models.py defines them.
// Every number a person reads comes from one of the string fields: net_mwh,
// volume_mwh and price are decimals written as strings, and stay strings here.

export interface SettlementPeriod {
  settlement_date: string // the UK calendar day, "2026-10-25"
  period: number // the API's own number for it, 1 to 46, 48 or 50
  start_utc: string // the instant it starts, "2026-10-25T01:00:00Z": its identity
}

export interface Position {
  settlement_period: SettlementPeriod
  net_mwh: string
}

export interface DailyTotal {
  settlement_date: string
  net_mwh: string
}

export interface TradeIn {
  portfolio_id: number
  period_start: string // a start_utc, copied from a Position
  volume_mwh: string // as typed
  price: string // as typed
}

export interface Trade {
  id: number
  portfolio_id: number
  settlement_period: SettlementPeriod
  volume_mwh: string
  price: string
  traded_at: string
}
