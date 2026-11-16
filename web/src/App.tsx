import { useState } from 'react'

import { getDaily, getPositions } from './api'
import { Chart, countLine } from './Chart'
import { DEFAULT_DATE, FIRST_DATE, LAST_DATE, QUICK_DATES, isChoosable, weekAround } from './dates'
import { Totals } from './Totals'
import { TradeForm } from './TradeForm'
import type { Trade } from './types'
import { useRead } from './useRead'
import { useWidth } from './useWidth'

// The seed's own portfolios, scripts/seed.py: PORTFOLIO_IDS = range(1, 51). The API
// has no portfolio endpoint to ask, so the range is written out here, and a portfolio
// outside it would simply have no trades.
const FIRST_PORTFOLIO = 1
const LAST_PORTFOLIO = 50
const DEFAULT_PORTFOLIO = 7
const PORTFOLIOS = Array.from({ length: LAST_PORTFOLIO - FIRST_PORTFOLIO + 1 }, (_, index) => FIRST_PORTFOLIO + index)

export function App() {
  const [portfolio, setPortfolio] = useState(DEFAULT_PORTFOLIO)
  const [date, setDate] = useState(DEFAULT_DATE)
  const [picked, setPicked] = useState('')
  const [posted, setPosted] = useState<string | null>(null)
  // Counts the trades posted, so that each one makes both reads run again.
  const [posts, setPosts] = useState(0)
  const [chartBox, width] = useWidth<HTMLDivElement>()

  const choosable = isChoosable(date)
  const week = choosable ? weekAround(date) : []

  const positions = useRead(choosable ? (signal) => getPositions(portfolio, date, signal) : null, [
    portfolio,
    date,
    choosable,
    posts,
  ])
  const daily = useRead(choosable ? (signal) => getDaily(portfolio, week[0], week[week.length - 1], signal) : null, [
    portfolio,
    date,
    choosable,
    posts,
  ])

  // The bars shown: the answer, or while the next one is awaited, the last one, greyed.
  const rows = positions.state === 'ready' ? positions.data : positions.state === 'failed' ? null : positions.last
  const waiting = positions.state === 'loading'
  // Only an answer about this date and portfolio offers periods to post to.
  const periods = positions.state === 'ready' ? positions.data : []
  const pickedHere = periods.some((row) => row.settlement_period.start_utc === picked) ? picked : ''

  const changeControl = () => setPosted(null)
  const changePortfolio = (value: number) => {
    setPortfolio(value)
    changeControl()
  }
  const changeDate = (value: string) => {
    setDate(value)
    setPicked('')
    changeControl()
  }
  const pick = (startUtc: string) => {
    setPicked(startUtc)
    changeControl()
  }
  const afterPost = (trade: Trade) => {
    setPosted(trade.settlement_period.start_utc)
    setPosts((count) => count + 1)
  }

  return (
    <main>
      <header>
        <h1>Energy positions</h1>
        <p className="lede">Synthetic data. Net position for each GB settlement period.</p>
        <p className="quiet">
          The live service sleeps when nobody is using it, and so does its database. The first request after a quiet
          spell can take up to 30 seconds.
        </p>
      </header>

      <section className="controls" aria-label="Choose what to show">
        <label>
          <span className="label">Portfolio</span>
          <select value={portfolio} onChange={(event) => changePortfolio(Number(event.target.value))}>
            {PORTFOLIOS.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">Settlement date</span>
          <input
            type="date"
            value={date}
            min={FIRST_DATE}
            max={LAST_DATE}
            onChange={(event) => changeDate(event.target.value)}
          />
        </label>
        <div className="quick">
          {QUICK_DATES.map((quick) => (
            <button
              key={quick.date}
              type="button"
              className="link"
              aria-pressed={date === quick.date}
              onClick={() => changeDate(quick.date)}
            >
              {quick.label}
            </button>
          ))}
        </div>
      </section>

      {!choosable && (
        <p className="error" role="alert">
          Choose a settlement date from {FIRST_DATE} to {LAST_DATE}: those are the days with data.
        </p>
      )}

      <section aria-labelledby="positions-heading">
        <h2 id="positions-heading">Net position</h2>
        {rows !== null && <p className={waiting ? 'count stale' : 'count'}>{countLine(rows.length)}</p>}
        <p className="legend">
          <span className="key bought" /> Bought, above the line
          <span className="key sold" /> Sold, below it
          <span className="scale">Bars are scaled to the largest net of the day.</span>
        </p>
        <div className="chart-box" ref={chartBox}>
          {positions.state === 'failed' && (
            <p className="error" role="alert">
              The positions could not be read. {positions.error.message}
            </p>
          )}
          {waiting && (
            <p className="loading over" role="status">
              Loading
            </p>
          )}
          {rows !== null && (
            <div className={waiting ? 'stale' : undefined} inert={waiting}>
              <Chart rows={rows} width={width} picked={pickedHere} posted={posted} onPick={pick} />
            </div>
          )}
        </div>
      </section>

      <section aria-labelledby="totals-heading">
        <h2 id="totals-heading">Daily totals</h2>
        <Totals dates={week} chosen={date} read={daily} />
      </section>

      <section aria-labelledby="trade-heading">
        <h2 id="trade-heading">Post a trade</h2>
        <TradeForm
          portfolio={portfolio}
          periods={periods}
          picked={pickedHere}
          onPick={pick}
          onChange={changeControl}
          onPosted={afterPost}
        />
      </section>
    </main>
  )
}
