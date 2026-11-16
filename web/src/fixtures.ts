import type { Position } from './types'

/**
 * `count` consecutive half-hours from 23:00 UTC on 24 Oct 2026, which is midnight at
 * the start of the UK day of 25 Oct, numbered from 1. Test data only: the page itself
 * never makes up a period, it draws the ones the API sends.
 */
export function day(count: number): Position[] {
  const first = Date.parse('2026-10-24T23:00:00Z')
  return Array.from({ length: count }, (_, index) => ({
    settlement_period: {
      settlement_date: '2026-10-25',
      period: index + 1,
      start_utc: new Date(first + index * 30 * 60_000).toISOString().replace('.000Z', 'Z'),
    },
    net_mwh: index % 2 === 0 ? '12.500' : '-7.250',
  }))
}
