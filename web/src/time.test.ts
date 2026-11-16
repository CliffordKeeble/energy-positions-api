import { describe, expect, test } from 'vitest'

import { formatLocal, formatUtc } from './time'

describe('the test machine', () => {
  test('is on UTC, whatever the real one is, so that a formatter that forgets its zone cannot pass by luck', () => {
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe('UTC')
    expect(new Date('2026-06-15T12:00:00Z').getTimezoneOffset()).toBe(0)
  })
})

describe('formatLocal: a UTC start, on a UK clock', () => {
  test('midnight UTC on the day the clocks go back is 01:00 on summer time', () => {
    expect(formatLocal('2026-10-25T00:00:00Z')).toBe('01:00 BST')
  })

  test('an hour later it is 01:00 again, on winter time: the repeated hour', () => {
    expect(formatLocal('2026-10-25T01:00:00Z')).toBe('01:00 GMT')
  })

  test('23:00 UTC on a June evening is midnight at the start of the next UK day', () => {
    expect(formatLocal('2026-06-15T23:00:00Z')).toBe('00:00 BST')
  })

  test('on the day the clocks go forward, 01:00 never happens: 00:30 GMT is followed by 02:00 BST', () => {
    expect(formatLocal('2026-03-29T00:30:00Z')).toBe('00:30 GMT')
    expect(formatLocal('2026-03-29T01:00:00Z')).toBe('02:00 BST')
  })
})

describe('formatUtc', () => {
  test('says UTC and keeps the hour of the instant', () => {
    expect(formatUtc('2026-10-25T00:00:00Z')).toBe('00:00 UTC')
    expect(formatUtc('2026-10-25T01:00:00Z')).toBe('01:00 UTC')
  })
})
