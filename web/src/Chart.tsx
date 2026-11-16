import { useState } from 'react'

import { formatLocal, formatUtc } from './time'
import type { Position } from './types'

// Geometry, in pixels. The colours are all in styles.css.
const HEIGHT = 320
const TOP = 10
const LABEL_BAND = 26
const TIP_WIDTH = 168
const TIP_GAP = 14
/** What a two-digit period number needs, side by side with its neighbour. */
const LABEL_ROOM = 14

/**
 * The line above the chart, built from the count of bars the API returned. The page
 * does not know which days have 46 or 50: it reads the count, and says what the
 * count means.
 */
export function countLine(count: number): string {
  if (count === 46) return '46 settlement periods: the clocks go forward'
  if (count === 50) return '50 settlement periods: the clocks go back'
  return `${count} settlement periods`
}

/**
 * Which bars carry their period number: every bar where it fits, otherwise every
 * second. On the 50-bar day periods 3 to 6, the two passes over 01:00 and 01:30, are
 * always named, because they are the point of looking.
 */
export function labelled(rows: readonly Position[], slot: number): boolean[] {
  const everyBar = slot >= LABEL_ROOM
  const clocksBack = rows.length === 50
  return rows.map((row, index) => {
    if (everyBar || index % 2 === 0) return true
    const { period } = row.settlement_period
    return clocksBack && period >= 3 && period <= 6
  })
}

interface ChartProps {
  rows: readonly Position[]
  width: number
  /** The start_utc picked for the trade form, if any. */
  picked: string
  /** The start_utc of the bar a trade was just posted to, if any. */
  posted: string | null
  onPick: (startUtc: string) => void
}

export function Chart({ rows, width, picked, posted, onPick }: ChartProps) {
  const [hover, setHover] = useState<number | null>(null)
  const [focus, setFocus] = useState<number | null>(null)
  const active = hover ?? focus

  // net_mwh is parsed to a number here, for a bar's height, and nowhere else.
  const heights = rows.map((row) => Number(row.net_mwh))
  const up = Math.max(0, ...heights)
  const down = Math.max(0, ...heights.map((h) => -h))
  const plotHeight = HEIGHT - TOP - LABEL_BAND
  const span = up + down
  const scale = span === 0 ? 0 : plotHeight / span
  const zeroY = span === 0 ? TOP + plotHeight / 2 : TOP + up * scale

  const slot = rows.length === 0 ? width : width / rows.length
  const gap = Math.min(2, slot * 0.12)
  const named = labelled(rows, slot)

  let tip = null
  if (active !== null && rows[active]) {
    const row = rows[active]
    const centre = (active + 0.5) * slot
    const beside = centre + TIP_GAP + TIP_WIDTH <= width ? centre + TIP_GAP : centre - TIP_GAP - TIP_WIDTH
    const left = Math.min(Math.max(beside, 0), Math.max(0, width - TIP_WIDTH))
    tip = (
      <div className="tip" style={{ left, width: TIP_WIDTH, top: TOP }}>
        <strong>Period {row.settlement_period.period}</strong>
        <span>{formatLocal(row.settlement_period.start_utc)}</span>
        <span>{formatUtc(row.settlement_period.start_utc)}</span>
        <span>{row.net_mwh} MWh</span>
      </div>
    )
  }

  return (
    <div className="chart" style={{ width }}>
      <svg width={width} height={HEIGHT} role="group" aria-label="Net position for each settlement period">
        <line className="zero" x1={0} x2={width} y1={zeroY} y2={zeroY} />
        {rows.map((row, index) => {
          const { period, start_utc: start } = row.settlement_period
          const value = heights[index]
          const barHeight = value === 0 ? 2 : Math.abs(value) * scale
          const barY = value > 0 ? zeroY - barHeight : value < 0 ? zeroY : zeroY - 1
          const kind = value > 0 ? 'bought' : value < 0 ? 'sold' : 'flat'
          const classes = ['slot', active === index && 'active', picked === start && 'picked', posted === start && 'posted']
          const left = index * slot
          return (
            <g
              key={start}
              className={classes.filter(Boolean).join(' ')}
              role="button"
              tabIndex={0}
              aria-label={`Period ${period}, ${formatLocal(start)}, ${formatUtc(start)}, net ${row.net_mwh} MWh`}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setFocus(index)}
              onBlur={() => setFocus(null)}
              onClick={() => onPick(start)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onPick(start)
                }
              }}
            >
              <rect className="hit" x={left} y={0} width={slot} height={HEIGHT - LABEL_BAND} />
              <rect className={`bar ${kind}`} x={left + gap} y={barY} width={Math.max(slot - 2 * gap, 1)} height={barHeight} />
              {named[index] && (
                <text className="period" x={left + slot / 2} y={HEIGHT - 8} textAnchor="middle">
                  {period}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {tip}
    </div>
  )
}
