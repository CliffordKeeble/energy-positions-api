import { showDate } from './dates'
import type { Read } from './useRead'
import type { DailyTotal } from './types'

interface TotalsProps {
  /** The seven settlement dates, centred on the chosen one. */
  dates: readonly string[]
  chosen: string
  read: Read<DailyTotal[]>
}

/** The daily totals for the days around the chosen one: the API's strings, and "no trades" where it sent no row. */
export function Totals({ dates, chosen, read }: TotalsProps) {
  if (read.state === 'failed') {
    return (
      <p className="error" role="alert">
        The daily totals could not be read. {read.error.message}
      </p>
    )
  }

  const rows = read.state === 'ready' ? read.data : read.last
  const waiting = read.state === 'loading'
  if (rows === null) {
    return waiting ? (
      <p className="loading" role="status">
        Loading
      </p>
    ) : null
  }

  const netByDate = new Map(rows.map((row) => [row.settlement_date, row.net_mwh]))
  return (
    <div className="panel">
      {waiting && (
        <p className="loading over" role="status">
          Loading
        </p>
      )}
      <table className={waiting ? 'stale' : undefined}>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col" className="num">
              Net MWh
            </th>
          </tr>
        </thead>
        <tbody>
          {dates.map((date) => {
            const net = netByDate.get(date)
            const isChosen = date === chosen
            return (
              <tr key={date} className={isChosen ? 'chosen' : undefined} aria-current={isChosen ? 'date' : undefined}>
                <th scope="row">
                  {showDate(date)}
                  {isChosen && <span className="tag">chosen</span>}
                </th>
                <td className={net === undefined ? 'num none' : 'num'}>{net ?? 'no trades'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
