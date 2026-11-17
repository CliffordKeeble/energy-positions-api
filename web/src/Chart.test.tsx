import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { Chart, countLine, labelled } from './Chart'
import { day } from './fixtures'

const nothing = () => {}

function bars(rows = day(50), width = 960) {
  render(<Chart rows={rows} width={width} picked="" posted={null} onPick={nothing} />)
  return screen.getAllByRole('button')
}

describe('the bars', () => {
  test('there is one for each row the API returned: 50', () => {
    expect(bars(day(50))).toHaveLength(50)
  })

  test('there is one for each row the API returned: 46', () => {
    expect(bars(day(46))).toHaveLength(46)
  })

  test('there is one for each row the API returned, whatever the count', () => {
    expect(bars(day(48))).toHaveLength(48)
    document.body.innerHTML = ''
    expect(bars(day(47))).toHaveLength(47)
  })

  test('bought rises, sold falls, from one zero line', () => {
    bars(day(2))
    const [bought, sold] = Array.from(document.querySelectorAll('rect.bar')).map((rect) => ({
      kind: rect.getAttribute('class') ?? '',
      y: Number(rect.getAttribute('y')),
      height: Number(rect.getAttribute('height')),
    }))
    const zero = Number(document.querySelector('line.zero')?.getAttribute('y1'))

    expect(bought.kind).toContain('bought')
    expect(bought.y + bought.height).toBeCloseTo(zero)
    expect(sold.kind).toContain('sold')
    expect(sold.y).toBeCloseTo(zero)
  })

  test('a click, or Enter, picks the bar by its UTC start', () => {
    const onPick = vi.fn()
    render(<Chart rows={day(50)} width={960} picked="" posted={null} onPick={onPick} />)
    const all = screen.getAllByRole('button')

    fireEvent.click(all[4])
    fireEvent.keyDown(all[2], { key: 'Enter' })

    expect(onPick).toHaveBeenNthCalledWith(1, '2026-10-25T01:00:00Z')
    expect(onPick).toHaveBeenNthCalledWith(2, '2026-10-25T00:00:00Z')
  })

  test('the bar posted to, and the bar picked, are marked', () => {
    render(
      <Chart rows={day(50)} width={960} picked="2026-10-25T00:00:00Z" posted="2026-10-25T01:00:00Z" onPick={nothing} />,
    )
    const all = screen.getAllByRole('button')

    expect(all[2].getAttribute('class')).toContain('picked')
    expect(all[4].getAttribute('class')).toContain('posted')
  })
})

describe('the box on hover and focus', () => {
  function tipFor(index: number, width = 960) {
    const all = bars(day(50), width)
    fireEvent.focus(all[index])
    const tip = document.querySelector('.tip')
    return tip ? Array.from(tip.children).map((child) => child.textContent) : null
  }

  test('periods 3 and 5 of 25 October both read 01:00 local, told apart by BST and GMT and by the UTC start', () => {
    expect(tipFor(2)).toEqual(['Period 3', '01:00 BST', '00:00 UTC', '12.500 MWh'])
    document.body.innerHTML = ''
    expect(tipFor(4)).toEqual(['Period 5', '01:00 GMT', '01:00 UTC', '12.500 MWh'])
  })

  test('shows the net as the API wrote it, sign and trailing zeros included', () => {
    expect(tipFor(1)).toEqual(['Period 2', '00:30 BST', '23:30 UTC', '-7.250 MWh'])
  })

  test('there is no box until a bar is hovered or focused', () => {
    bars()
    expect(document.querySelector('.tip')).toBeNull()
  })

  test('stays inside the chart at both ends', () => {
    for (const index of [0, 49]) {
      document.body.innerHTML = ''
      const all = bars(day(50), 360)
      fireEvent.mouseEnter(all[index])
      const tip = document.querySelector<HTMLElement>('.tip')!
      const left = parseFloat(tip.style.left)
      const width = parseFloat(tip.style.width)

      expect(left).toBeGreaterThanOrEqual(0)
      expect(left + width).toBeLessThanOrEqual(360)
    }
  })
})

describe('the line above the chart', () => {
  test.each([
    [48, '48 settlement periods'],
    [46, '46 settlement periods: the clocks go forward'],
    [50, '50 settlement periods: the clocks go back'],
    [47, '47 settlement periods'],
    [0, '0 settlement periods'],
  ])('%i bars: %s', (count, line) => {
    expect(countLine(count)).toBe(line)
  })
})

describe('the period numbers under the bars', () => {
  const named = (flags: boolean[]) => flags.flatMap((flag, index) => (flag ? [index + 1] : []))

  test('every bar is named where there is room', () => {
    expect(named(labelled(day(50), 20))).toHaveLength(50)
  })

  test('every second bar is named where there is not', () => {
    expect(named(labelled(day(48), 7))).toEqual(Array.from({ length: 24 }, (_, i) => 2 * i + 1))
  })

  test('on the 50-bar day periods 3, 4, 5 and 6 are always named, where a digit has room', () => {
    const periods = named(labelled(day(50), 9))

    expect(periods).toEqual(expect.arrayContaining([3, 4, 5, 6]))
    expect(periods).toHaveLength(25 + 2) // the odd ones, and 4 and 6
  })

  test('at phone width the 50-bar day is named every second bar, and 4 and 6 give way', () => {
    const periods = named(labelled(day(50), 343 / 50)) // 343 px of chart at 375 px of screen

    expect(periods).toEqual(Array.from({ length: 25 }, (_, i) => 2 * i + 1))
    expect(periods).toContain(3) // the first 01:00 (BST)
    expect(periods).toContain(5) // the second (GMT)
    expect(periods).not.toContain(4)
    expect(periods).not.toContain(6)
  })

  test('the 46-bar day has no such exception', () => {
    expect(named(labelled(day(46), 7))).not.toContain(4)
  })

  test('the text is drawn under the bars, from the API period numbers', () => {
    bars(day(50), 500)
    const texts = Array.from(document.querySelectorAll('text.period')).map((text) => text.textContent)

    expect(texts).toHaveLength(27)
    expect(texts.slice(0, 7)).toEqual(['1', '3', '4', '5', '6', '7', '9'])
  })
})
