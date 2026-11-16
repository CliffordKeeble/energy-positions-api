// Calendar dates, as "2026-10-25" strings. Adding a day to one of these is plain
// calendar arithmetic and is done in UTC, where every day is 24 hours, so no time
// zone can come into it. It is not settlement arithmetic: how many periods a day has
// is never worked out here, it is the length of the list the API returns.

// The seed's own range, scripts/seed.py: FIRST_DATE, LAST_DATE = 2025-01-01, 2026-12-31.
export const FIRST_DATE = '2025-01-01'
export const LAST_DATE = '2026-12-31'

export const DEFAULT_DATE = '2026-10-25'

/** The three quick links: the day the clocks go back, the day they go forward, an ordinary day. */
export const QUICK_DATES: readonly { label: string; date: string }[] = [
  { label: '25 Oct 2026', date: '2026-10-25' },
  { label: '29 Mar 2026', date: '2026-03-29' },
  { label: '15 Jun 2026', date: '2026-06-15' },
]

const DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** True for a real calendar date inside the seeded range. ISO dates sort as text. */
export function isChoosable(date: string): boolean {
  const parts = DATE.exec(date)
  if (!parts) return false
  const [, year, month, day] = parts
  const real = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)))
  return real.toISOString().slice(0, 10) === date && date >= FIRST_DATE && date <= LAST_DATE
}

export function addDays(date: string, days: number): string {
  const [year, month, day] = date.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10)
}

/** Seven dates centred on the one given: three before, it, three after. */
export function weekAround(date: string): string[] {
  return [-3, -2, -1, 0, 1, 2, 3].map((offset) => addDays(date, offset))
}

const SHOWN = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' })

/** "25 Oct 2026". UTC midnight on a calendar date is that date everywhere. */
export function showDate(date: string): string {
  return SHOWN.format(new Date(`${date}T00:00:00Z`))
}
