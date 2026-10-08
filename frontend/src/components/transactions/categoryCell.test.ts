/**
 * The category cell's label and click rule, shared by a register row and the
 * split lines drawn under it. Both lived inline in TransactionRow; the split
 * lines needed the same answers, and a copy would have been free to disagree
 * about when a reconciled split opens the full editor instead.
 */
import { describe, expect, it } from 'vitest'
import { categoryCellAction, categoryCellLabel } from './categoryCell'
import { makeTransaction } from '../../test-utils/factories'

const categories = new Map([['c1', 'Groceries']])
const desktop = { isMobile: false, accountOnBudget: true }

describe('categoryCellLabel', () => {
  it('names a split as a split, whatever else it carries', () => {
    const t = makeTransaction({ is_split: true, category_id: 'c1' })
    expect(categoryCellLabel(t, categories, true)).toEqual({ kind: 'split' })
  })

  it('names the category, or a dash for one the map does not hold', () => {
    expect(categoryCellLabel(makeTransaction({ category_id: 'c1' }), categories, true)).toEqual({
      kind: 'category',
      name: 'Groceries',
    })
    expect(categoryCellLabel(makeTransaction({ category_id: 'gone' }), categories, true)).toEqual({
      kind: 'category',
      name: '—',
    })
  })

  it("follows the server's needs_category, carrying the deleted category as provenance", () => {
    const t = makeTransaction({ needs_category: true, prior_category_name: 'Dining' })
    expect(categoryCellLabel(t, categories, true)).toEqual({
      kind: 'needs-category',
      was: 'Dining',
    })
    expect(categoryCellLabel(makeTransaction({ needs_category: true }), categories, true)).toEqual({
      kind: 'needs-category',
      was: null,
    })
  })

  it('reads an uncategorized row that needs none as a transfer on budget, untracked off it', () => {
    const t = makeTransaction()
    expect(categoryCellLabel(t, categories, true)).toEqual({ kind: 'transfer' })
    expect(categoryCellLabel(t, categories, false)).toEqual({ kind: 'untracked' })
  })
})

describe('categoryCellAction', () => {
  it('opens the inline split editor on an unreconciled split', () => {
    expect(categoryCellAction(makeTransaction({ is_split: true }), desktop)).toBe('split')
  })

  it('opens the full editor on a reconciled split — its lines stay viewable there', () => {
    const t = makeTransaction({ is_split: true, cleared: 'reconciled' })
    expect(categoryCellAction(t, desktop)).toBe('edit')
  })

  it('opens the picker on a plain row, and nothing on a reconciled one', () => {
    expect(categoryCellAction(makeTransaction(), desktop)).toBe('category')
    expect(categoryCellAction(makeTransaction({ cleared: 'reconciled' }), desktop)).toBeNull()
  })

  it('does nothing on a phone, where the row is one tap target', () => {
    const t = makeTransaction({ is_split: true })
    expect(categoryCellAction(t, { isMobile: true, accountOnBudget: true })).toBeNull()
  })

  it('does nothing on a tracking account, which has no categories', () => {
    const t = makeTransaction({ is_split: true })
    expect(categoryCellAction(t, { isMobile: false, accountOnBudget: false })).toBeNull()
  })
})
