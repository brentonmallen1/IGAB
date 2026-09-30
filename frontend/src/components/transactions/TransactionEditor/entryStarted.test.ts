import { describe, expect, it } from 'vitest'
import { entryStarted, type EntryFields } from './entryStarted'

const blank: EntryFields = {
  date: '2030-01-10',
  payeeQuery: '',
  categoryId: '',
  memo: '',
  outflow: '',
  inflow: '',
}
const flat = { isSplit: false, isTransfer: false }

describe('entryStarted', () => {
  it('is false for the form as it opened', () => {
    expect(entryStarted(blank, blank, flat)).toBe(false)
  })

  it.each(Object.keys(blank) as (keyof EntryFields)[])('counts a change to %s', (field) => {
    expect(entryStarted({ ...blank, [field]: 'x' }, blank, flat)).toBe(true)
  })

  it('counts a split or a transfer even with every field untouched', () => {
    expect(entryStarted(blank, blank, { isSplit: true, isTransfer: false })).toBe(true)
    expect(entryStarted(blank, blank, { isSplit: false, isTransfer: true })).toBe(true)
  })

  it('measures against the prefilled baseline, not an empty form', () => {
    // A budget-row add opens with its category; that is nobody's entry.
    const prefilled = { ...blank, categoryId: 'cat-1', payeeQuery: 'Corner Bakery' }
    expect(entryStarted(prefilled, prefilled, flat)).toBe(false)
    expect(entryStarted({ ...prefilled, categoryId: '' }, prefilled, flat)).toBe(true)
  })
})
