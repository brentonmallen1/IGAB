import { describe, expect, it } from 'vitest'
import { truncateLabel } from './truncateLabel'

describe('truncateLabel', () => {
  it('leaves a label that fits alone', () => {
    expect(truncateLabel('Groceries', 16)).toBe('Groceries')
  })

  it('leaves a label of exactly the maximum alone', () => {
    // 16 chars: the boundary the five copies all treated as "fits".
    expect(truncateLabel('Harborstone Fees', 16)).toBe('Harborstone Fees')
  })

  it('never returns a string wider than the maximum', () => {
    const out = truncateLabel('Cascade Point Holiday Fund', 16)
    // A cut can land on a space, so the ellipsis follows one. All five copies
    // did this; it is pinned rather than tidied, because trimming would move
    // labels on six reports at once.
    expect(out).toBe('Cascade Point …')
    expect(out.length).toBeLessThanOrEqual(16)
  })

  it('honours the per-chart threshold, which is the one intended variation', () => {
    const name = 'Northwind Payserv Transfers'
    expect(truncateLabel(name, 14)).toBe('Northwind Pa…')
    expect(truncateLabel(name, 24)).toBe('Northwind Payserv Tran…')
  })
})

describe('the two copies that kept one character more', () => {
  // The treemap's tile label is pinned in treemapTile.test.ts.
  it('cuts the Activity page names by the same rule', () => {
    // changeDetails.truncate sliced `max - 1` at its default 24.
    expect(truncateLabel('The Extremely Long Payee Name Emporium & Co', 24)).toBe(
      'The Extremely Long Pay…'
    )
  })
})
