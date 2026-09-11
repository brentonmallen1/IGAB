import { describe, expect, it } from 'vitest'
import { dotSize, largestMagnitude, newestFirst, timelineTone } from './timelineView'

describe('timelineTone', () => {
  it('gives a mixed split (null class) the neutral tone, not a guess from its sign', () => {
    // An all-savings split, negative, used to be drawn as a red expense.
    expect(timelineTone(null)).toBe('neutral')
  })

  it('gives a class it does not know the neutral tone', () => {
    expect(timelineTone('a_class_added_later')).toBe('neutral')
  })

  it('draws savings and debt principal as savings, whatever the sign of the row', () => {
    // The tone takes no amount at all: a transfer into savings is negative and
    // is still not an expense.
    expect(timelineTone('savings')).toBe('savings')
    expect(timelineTone('debt_principal')).toBe('savings')
  })

  it('reads spending, interest and income by class', () => {
    expect(timelineTone('spending')).toBe('expense')
    expect(timelineTone('debt_interest')).toBe('expense')
    expect(timelineTone('income')).toBe('income')
    expect(timelineTone('transfer_internal')).toBe('neutral')
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
