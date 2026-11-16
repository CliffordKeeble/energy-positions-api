import { useEffect, useRef, useState } from 'react'

import { ApiError } from './api'

/**
 * Where a read stands. `last` is the previous good result, kept while the next one
 * is awaited so the page can show it greyed instead of a blank.
 */
export type Read<T> =
  | { state: 'idle'; last: T | null }
  | { state: 'loading'; last: T | null }
  | { state: 'ready'; data: T; last: T }
  | { state: 'failed'; error: ApiError; last: T | null }

/**
 * Runs `load` whenever `deps` change, and again if `deps` change before it answers
 * (the first is aborted). A `load` of null reads nothing and leaves the last result.
 */
export function useRead<T>(load: ((signal: AbortSignal) => Promise<T>) | null, deps: readonly unknown[]): Read<T> {
  const last = useRef<T | null>(null)
  const [read, setRead] = useState<Read<T>>({ state: load ? 'loading' : 'idle', last: null })

  useEffect(() => {
    if (!load) {
      setRead({ state: 'idle', last: last.current })
      return
    }
    const controller = new AbortController()
    setRead({ state: 'loading', last: last.current })
    load(controller.signal).then(
      (data) => {
        last.current = data
        setRead({ state: 'ready', data, last: data })
      },
      (error: unknown) => {
        if (controller.signal.aborted) return
        const failure = error instanceof ApiError ? error : new ApiError(null, 'The read failed.')
        setRead({ state: 'failed', error: failure, last: last.current })
      },
    )
    return () => controller.abort()
    // The caller's closure changes every render; only its inputs, `deps`, start a read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return read
}
