import { describe, expect, it } from 'vitest'
import { dotSize, largestMagnitude, newestFirst, timelineChip } from './timelineView'

describe('timelineChip', () => {
  const row = (amount: number, activity_class: string | null, activity_label: string) => ({
    amount,
    activity_class,
    activity_label,
  })

  it('names an inflow to a spending envelope a Refund', () => {
    // +5,000 back into Home Repair was SPENDING by class and drew as a red
    // "$5,000.00" with no chip — a purchase of the same size.
    expect(timelineChip(row(5000, 'spending', 'Spending'))).toBe('Refund')
  })

  it('says nothing beside ordinary spending', () => {
    expect(timelineChip(row(-250, 'spending', 'Spending'))).toBeNull()
  })

  it('names money back on interest and fees a Refund too', () => {
    expect(timelineChip(row(35, 'debt_interest', 'Interest & fees'))).toBe('Refund')
    expect(timelineChip(row(-35, 'debt_interest', 'Interest & fees'))).toBe('Interest & fees')
  })

  it('keeps the served label for every other class, whichever way it went', () => {
    expect(timelineChip(row(3000, 'income', 'Income'))).toBe('Income')
    // A clawed-back paycheck: its sign says which way; the chip says what.
    expect(timelineChip(row(-75, 'income', 'Income'))).toBe('Income')
    expect(timelineChip(row(-900, 'savings', 'Savings'))).toBe('Savings')
    expect(timelineChip(row(900, 'savings', 'Savings'))).toBe('Savings')
  })

  it('reads a mixed split by its served label, never by its sign', () => {
    expect(timelineChip(row(400, null, 'Split'))).toBe('Split')
  })
})

describe('newestFirst', () => {
  it('draws the server’s size ranking in date order', () => {
    const bySize = [
      { id: 'rent', date: '2026-07-01' },
      { id: 'car', date: '2026-08-14' },
      { id: 'tv', date: '2026-06-20' },
    ]
    expect(newestFirst(bySize).map((r) => r.id)).toEqual(['car', 'rent', 'tv'])
    // and leaves the served array alone
    expect(bySize[0].id).toBe('rent')
  })
})

describe('the dot scale', () => {
  it('tops out at the largest magnitude on the page, not at row 0', () => {
    // Date order puts a small row first; scaling to it made every other dot
    // overflow the top of the range.
    const rows = [{ amount: -120 }, { amount: 2400 }, { amount: -600 }]
    expect(largestMagnitude(rows)).toBe(2400)
    expect(dotSize(-2400, 2400)).toBe(22)
    expect(dotSize(-120, 2400)).toBe(9)
  })

  it('draws the smallest dot when nothing on the page has a size', () => {
    expect(largestMagnitude([])).toBe(0)
    expect(dotSize(0, 0)).toBe(8)
  })
})
