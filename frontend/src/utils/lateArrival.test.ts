import { describe, expect, it } from 'vitest'
import { makeTransaction } from '../test-utils/factories'
import { countsInAnotherMonth, lateArrivalLabel } from './lateArrival'

describe('a row the server counts in another month', () => {
  it('is a late arrival when the served month is not its own', () => {
    // Dated in June, arrived after a July import: the server counts it in July.
    const late = makeTransaction({ date: '2026-06-28', counts_in_month: '2026-07-01' })
    expect(countsInAnotherMonth(late)).toBe(true)
    expect(lateArrivalLabel(late.counts_in_month)).toBe(
      'Arrived after your import — counts in July 2026'
    )
  })

  it('is an ordinary row when the served month is its own', () => {
    expect(countsInAnotherMonth(makeTransaction({ date: '2026-07-31' }))).toBe(false)
  })
})
