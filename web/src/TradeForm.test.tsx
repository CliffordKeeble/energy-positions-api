import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { day } from './fixtures'
import { TradeForm } from './TradeForm'

afterEach(() => vi.unstubAllGlobals())

const FIFTH = '2026-10-25T01:00:00Z'
const nothing = () => {}

function filled(onPosted = vi.fn(), onChange = vi.fn()) {
  render(
    <TradeForm portfolio={7} periods={day(50)} picked={FIFTH} onPick={nothing} onChange={onChange} onPosted={onPosted} />,
  )
  fireEvent.change(screen.getByLabelText(/Volume/), { target: { value: '-12.500' } })
  fireEvent.change(screen.getByLabelText(/Price/), { target: { value: '84.20' } })
  return { onPosted, onChange }
}

describe('the trade form', () => {
  test('lists the day as the API gave it, with the UK time and the zone', () => {
    render(<TradeForm portfolio={7} periods={day(50)} picked="" onPick={nothing} onChange={nothing} onPosted={nothing} />)
    const options = screen.getAllByRole('option').map((option) => option.textContent)

    expect(options).toHaveLength(51)
    expect(options[3]).toBe('P3 · 01:00 BST')
    expect(options[5]).toBe('P5 · 01:00 GMT')
  })

  test('posts the picked period by its UTC start, with the strings typed, and tells the page', async () => {
    const trade = {
      id: 41,
      portfolio_id: 7,
      settlement_period: day(50)[4].settlement_period,
      volume_mwh: '-12.500',
      price: '84.20',
      traded_at: '2026-11-16T09:00:00Z',
    }
    const fetchStub = vi.fn().mockResolvedValue(new Response(JSON.stringify(trade), { status: 201 }))
    vi.stubGlobal('fetch', fetchStub)
    const { onPosted } = filled()

    fireEvent.click(screen.getByRole('button', { name: 'Post trade' }))

    await waitFor(() => expect(onPosted).toHaveBeenCalledWith(trade))
    expect(JSON.parse(fetchStub.mock.calls[0][1].body)).toEqual({
      portfolio_id: 7,
      period_start: FIFTH,
      volume_mwh: '-12.500',
      price: '84.20',
    })
    expect((await screen.findByRole('status')).textContent).toBe(
      'Recorded trade 41: portfolio 7, P5 · 01:00 GMT, -12.500 MWh at 84.20 per MWh.',
    )
  })

  test("shows the API's detail as text, never as markup", async () => {
    const detail = '<img src=x onerror="document.title=1"><b>bold</b>'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })))
    const { onPosted } = filled()

    fireEvent.click(screen.getByRole('button', { name: 'Post trade' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe(`Status 422: ${detail}`)
    expect(alert.querySelector('img, b')).toBeNull()
    expect(onPosted).not.toHaveBeenCalled()
  })

  test('changing a control tells the page, which unmarks the bar posted to', () => {
    const { onChange } = filled()

    expect(onChange).toHaveBeenCalledTimes(2)
  })

  test('cannot be posted with no period', () => {
    render(<TradeForm portfolio={7} periods={day(50)} picked="" onPick={nothing} onChange={nothing} onPosted={nothing} />)
    fireEvent.change(screen.getByLabelText(/Volume/), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText(/Price/), { target: { value: '1' } })

    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Post trade' }).disabled).toBe(true)
  })
})
