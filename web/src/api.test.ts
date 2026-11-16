import { afterEach, describe, expect, test, vi } from 'vitest'

import { ApiError, postTrade, wordsOf } from './api'

afterEach(() => vi.unstubAllGlobals())

const TRADE = { portfolio_id: 7, period_start: '2026-10-25T01:00:00Z', volume_mwh: '12.500', price: '84.20' }

describe('wordsOf: the API is the one to say what went wrong', () => {
  test('a detail that is a sentence is used as it is', () => {
    expect(wordsOf({ detail: "'to' is before 'from'" }, 'Unprocessable Entity')).toBe("'to' is before 'from'")
  })

  test('a detail that is a list of refusals says where each was and what was wrong', () => {
    const detail = [
      { loc: ['body', 'volume_mwh'], msg: 'Input should be a valid decimal' },
      { loc: ['query', 'settlement_date'], msg: 'Field required' },
    ]
    expect(wordsOf({ detail }, '')).toBe('volume_mwh: Input should be a valid decimal; settlement_date: Field required')
  })

  test('a reply with no detail has the status line only', () => {
    expect(wordsOf(null, 'Bad Gateway')).toBe('Bad Gateway')
    expect(wordsOf({}, '')).toBe('no reason given')
  })
})

describe('postTrade', () => {
  test('sends the volume and the price as the strings typed, never as numbers', async () => {
    const fetchStub = vi.fn().mockResolvedValue(new Response('{"id": 1}', { status: 201 }))
    vi.stubGlobal('fetch', fetchStub)

    await postTrade(TRADE)

    const [path, init] = fetchStub.mock.calls[0]
    expect(path).toBe('/trades')
    expect(init.method).toBe('POST')
    // A number would have lost the trailing zeros: 12.500 and 84.20 are 12.5 and 84.2.
    expect(init.body).toContain('"volume_mwh":"12.500"')
    expect(init.body).toContain('"price":"84.20"')
    expect(typeof JSON.parse(init.body).volume_mwh).toBe('string')
  })

  test('refuses with the status and the API words', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response('{"detail":"nope"}', { status: 422 }))))

    await expect(postTrade(TRADE)).rejects.toMatchObject({ status: 422, words: 'nope', message: 'Status 422: nope' })
    await expect(postTrade(TRADE)).rejects.toBeInstanceOf(ApiError)
  })

  test('says so when nothing answers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(postTrade(TRADE)).rejects.toMatchObject({ status: null, message: 'No answer from the API.' })
  })
})
