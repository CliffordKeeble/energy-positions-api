import { useLayoutEffect, useRef, useState } from 'react'

/** Used until the element has a width: before the first measurement, and where nothing can measure (jsdom). */
const FALLBACK = 960

/** The width of an element in pixels, kept up to date, so the chart can be drawn at its real size. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(FALLBACK)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const measure = () => {
      const measured = Math.floor(element.clientWidth)
      if (measured > 0) setWidth(measured)
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return [ref, width] as const
}
