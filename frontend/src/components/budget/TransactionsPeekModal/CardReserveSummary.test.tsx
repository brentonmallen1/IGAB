/**
 * The lines under a card's "what set this aside" list: Set aside going in,
 * the list's own total, what rode and what a refund paid off, the month's
 * other legs, and Set aside at the end — every figure served. Which lines and
 * which signs is `reserveMonth`'s (tested in cardRow.test.ts); this pins that
 * the panel draws them, ends on the served figure, and says when it cannot.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CardTimeline, CardTimelineMonth } from '../../../api/budgets'

const timeline = vi.hoisted(() => ({
  current: { data: undefined, isPending: true, isError: false } as {
    data: CardTimeline | undefined
    isPending: boolean
    isError: boolean
  },
  args: [] as unknown[],
}))
vi.mock('../../../api/budgets', () => ({
  useCardTimeline: (...args: unknown[]) => {
    timeline.args = args
    return timeline.current
  },
}))

import { CardReserveSummary } from './CardReserveSummary'

function tm(month: string, over: Partial<CardTimelineMonth> = {}): CardTimelineMonth {
  return {
    month,
    opening: 0,
    assigned: 0,
    reserved: 0,
    released: 0,
    residual: 0,
    payments: 0,
    written_off: 0,
    reserve_delta: 0,
    set_aside: 0,
    balance: 0,
    riding: 0,
    uncovered: 0,
    over_reserved: 0,
    short_reserved: 0,
    card_credit: 0,
    rode: 0,
    ride_repaid: 0,
    ...over,
  }
}

function served(months: CardTimelineMonth[]) {
  timeline.current = {
    data: { account_id: 'visa', name: 'Sapphire Visa', months, breach: null, anchor_month: null },
    isPending: false,
    isError: false,
  }
}

beforeEach(() => {
  timeline.current = { data: undefined, isPending: true, isError: false }
})

describe('CardReserveSummary', () => {
  it('reads the viewed month of the card’s own timeline', () => {
    render(<CardReserveSummary budgetId="b1" accountId="visa" month="2026-09-01" listedNet={0} />)
    expect(timeline.args).toEqual(['b1', 'visa', '2026-09-01'])
  })

  it('walks from Set aside going in to Set aside at the end, on served figures', () => {
    // 300 charged with 100 funded: 200 rode on. 100 assigned, 150 paid.
    served([
      tm('2026-08-01', { set_aside: 400 }),
      tm('2026-09-01', { reserved: 100, rode: 200, assigned: 100, payments: 150, set_aside: 450 }),
    ])
    render(
      <CardReserveSummary budgetId="b1" accountId="visa" month="2026-09-01" listedNet={-300} />
    )
    const rows = screen.getAllByRole('term').map((dt) => dt.parentElement?.textContent)
    expect(rows).toEqual([
      'Set aside going in, end of August 2026$400.00',
      'Spending above, net of refunds+ $300.00',
      'Rode on as debt, not set aside− $200.00',
      'Assigned to this card+ $100.00',
      'Paid to the card− $150.00',
      'Set aside at the end of September 2026$450.00',
    ])
  })

  it('says so when the month cannot be read, rather than drawing a sum with a hole in it', () => {
    timeline.current = { data: undefined, isPending: false, isError: true }
    render(<CardReserveSummary budgetId="b1" accountId="visa" month="2026-09-01" listedNet={0} />)
    expect(screen.getByText("The month's figures could not be loaded.")).toBeTruthy()
  })
})
