import { useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, postTrade } from './api'
import { formatLocal } from './time'
import type { Position, Trade } from './types'

interface TradeFormProps {
  portfolio: number
  /** The chosen day's periods, as /positions returned them. Empty while that is being read. */
  periods: readonly Position[]
  /** The start_utc picked, by this form's select or by a click on a bar. */
  picked: string
  onPick: (startUtc: string) => void
  /** Any control was changed: the bar marked as posted to is unmarked. */
  onChange: () => void
  onPosted: (trade: Trade) => void
}

function describe(position: Position['settlement_period']): string {
  return `P${position.period} · ${formatLocal(position.start_utc)}`
}

export function TradeForm({ portfolio, periods, picked, onPick, onChange, onPosted }: TradeFormProps) {
  const [volume, setVolume] = useState('')
  const [price, setPrice] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [receipt, setReceipt] = useState<string | null>(null)

  const edited = () => {
    setFailure(null)
    setReceipt(null)
    onChange()
  }

  const ready = periods.length > 0 && picked !== '' && volume.trim() !== '' && price.trim() !== '' && !busy

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!ready) return
    setBusy(true)
    setFailure(null)
    setReceipt(null)
    try {
      // The volume and the price go as the strings typed. No number is made of either.
      const trade = await postTrade({
        portfolio_id: portfolio,
        period_start: picked,
        volume_mwh: volume.trim(),
        price: price.trim(),
      })
      setReceipt(
        `Recorded trade ${trade.id}: portfolio ${trade.portfolio_id}, ${describe(trade.settlement_period)}, ` +
          `${trade.volume_mwh} MWh at ${trade.price} per MWh.`,
      )
      onPosted(trade)
    } catch (error) {
      // The API's own words, as text. React puts a string in the page as text, never as markup.
      setFailure(error instanceof ApiError ? error.message : 'The trade was not posted.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="row">
        <p className="fixed">
          <span className="label">Portfolio</span>
          {portfolio}
        </p>
        <label>
          <span className="label">Period</span>
          <select
            value={picked}
            disabled={periods.length === 0}
            onChange={(event) => {
              onPick(event.target.value)
              edited()
            }}
          >
            <option value="">{periods.length === 0 ? 'Waiting for the periods' : 'Choose a period'}</option>
            {periods.map((row) => (
              <option key={row.settlement_period.start_utc} value={row.settlement_period.start_utc}>
                {describe(row.settlement_period)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Volume (MWh)</span>
          <input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            placeholder="12.500"
            value={volume}
            onChange={(event) => {
              setVolume(event.target.value)
              edited()
            }}
          />
          <span className="hint">Positive is bought, negative is sold. Up to 3 decimals.</span>
        </label>
        <label>
          <span className="label">Price (per MWh)</span>
          <input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            placeholder="84.20"
            value={price}
            onChange={(event) => {
              setPrice(event.target.value)
              edited()
            }}
          />
          <span className="hint">Up to 2 decimals.</span>
        </label>
        <button type="submit" disabled={!ready}>
          {busy ? 'Posting' : 'Post trade'}
        </button>
      </div>
      {failure !== null && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}
      {receipt !== null && (
        <p className="receipt" role="status">
          {receipt}
        </p>
      )}
    </form>
  )
}
