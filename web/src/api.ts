// The API, by relative paths only: the page is served by the same app (or, in
// development, through Vite's proxy), so one build works on every address.
//
// No timeout is set here. A read can be slow while the live service and its database
// wake, and the browser's own limit is the only one that applies.

import type { DailyTotal, Position, Trade, TradeIn } from './types'

/** A reply that was not a success, or no reply at all. `words` is shown as text, never as markup. */
export class ApiError extends Error {
  readonly status: number | null
  readonly words: string

  constructor(status: number | null, words: string) {
    super(status === null ? words : `Status ${status}: ${words}`)
    this.status = status
    this.words = words
  }
}

/**
 * The API's own words from an error reply. FastAPI sends {"detail": "..."} for the
 * errors the app raises and {"detail": [{"loc": [...], "msg": "..."}]} for a request
 * it refused to read. Anything else is the status line alone.
 */
export function wordsOf(body: unknown, statusText: string): string {
  const detail = typeof body === 'object' && body !== null ? (body as { detail?: unknown }).detail : undefined
  if (typeof detail === 'string' && detail !== '') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item: unknown) => {
        if (typeof item === 'string') return item
        const { loc, msg } = (item ?? {}) as { loc?: unknown; msg?: unknown }
        const where = Array.isArray(loc) ? loc.filter((part) => part !== 'body' && part !== 'query').join('.') : ''
        const what = typeof msg === 'string' ? msg : JSON.stringify(item)
        return where ? `${where}: ${what}` : what
      })
      .join('; ')
  }
  return statusText || 'no reason given'
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(null, 'No answer from the API.')
  }

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Not JSON (a gateway's page, say): the status line is all there is to show.
  }
  if (!response.ok) throw new ApiError(response.status, wordsOf(body, response.statusText))
  return body as T
}

export function getPositions(portfolioId: number, settlementDate: string, signal: AbortSignal): Promise<Position[]> {
  const query = new URLSearchParams({ settlement_date: settlementDate })
  return send(`/portfolios/${portfolioId}/positions?${query}`, { signal })
}

export function getDaily(portfolioId: number, from: string, to: string, signal: AbortSignal): Promise<DailyTotal[]> {
  const query = new URLSearchParams({ from, to })
  return send(`/portfolios/${portfolioId}/daily?${query}`, { signal })
}

/** volume_mwh and price go in as the strings the person typed: no number is made of either. */
export function postTrade(trade: TradeIn): Promise<Trade> {
  return send('/trades', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(trade),
  })
}
