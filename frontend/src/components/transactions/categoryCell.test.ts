/**
 * The category cell's label and click rule, shared by a register row and the
 * split lines drawn under it. Both lived inline in TransactionRow; the split
 * lines needed the same answers, and a copy would have been free to disagree
 * about when a reconciled split opens the full editor instead.
 */
import { describe, expect, it } from 'vitest'
import {
  categoryCellAction,
  categoryCellHover,
  categoryCellLabel,
  categoryCellText,
} from './categoryCell'
import { makeTransaction } from '../../test-utils/factories'

const categories = new Map([['c1', { name: 'Groceries', group: 'Everyday' }]])
const desktop = { isMobile: false, accountOnBudget: true }

describe('categoryCellLabel', () => {
  it('names a split as a split, whatever else it carries', () => {
    const t = makeTransaction({ is_split: true, category_id: 'c1' })
    expect(categoryCellLabel(t, categories, true)).toEqual({ kind: 'split' })
  })

  it('names the category with its group path, or a dash and no path for one it cannot name', () => {
    expect(categoryCellLabel(makeTransaction({ category_id: 'c1' }), categories, true)).toEqual({
      kind: 'category',
      name: 'Groceries',
      path: 'Everyday › Groceries',
    })
    expect(categoryCellLabel(makeTransaction({ category_id: 'gone' }), categories, true)).toEqual({
      kind: 'category',
      name: '—',
      path: null,
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

describe('categoryCellText and categoryCellHover', () => {
  const label = (over: Parameters<typeof makeTransaction>[0], onBudget = true) =>
    categoryCellLabel(makeTransaction(over), categories, onBudget)

  it('reads every kind as plain text', () => {
    expect(categoryCellText(label({ is_split: true }))).toBe('Split')
    expect(categoryCellText(label({ category_id: 'c1' }))).toBe('Groceries')
    expect(categoryCellText(label({ needs_category: true }))).toBe('Needs Category')
    expect(categoryCellText(label({}))).toBe('Transfer')
    expect(categoryCellText(label({}, false))).toBe('—')
  })

  it('hovers only on a category it can name', () => {
    expect(categoryCellHover(label({ category_id: 'c1' }))).toBe('Everyday › Groceries')
    expect(categoryCellHover(label({ category_id: 'gone' }))).toBeNull()
    expect(categoryCellHover(label({ is_split: true }))).toBeNull()
    expect(categoryCellHover(label({ needs_category: true }))).toBeNull()
  })
})

/**
 * Each list below drew a transaction's category with its own copy of this
 * rule before it read the label. Every way a copy disagreed with the register
 * is a case, named for the component that got it wrong.
 */
describe('the copies this replaced', () => {
  const text = (over: Parameters<typeof makeTransaction>[0], onBudget = true) =>
    categoryCellText(categoryCellLabel(makeTransaction(over), categories, onBudget))

  it('DrillDownPanel: a row needing a category read blank', () => {
    // It never read `needs_category`; an unfiled purchase drew nothing.
    expect(text({ needs_category: true })).toBe('Needs Category')
  })

  it('DrillDownPanel: an unfiled transfer leg read "Transfer"', () => {
    // It tested `counterpart_account_id || transfer_id` before the server's
    // verdict, so a leg the server says needs filing read as settled.
    expect(text({ needs_category: true, counterpart_account_id: 'a2', transfer_id: 't9' })).toBe(
      'Needs Category'
    )
  })

  it('DrillDownPanel: an unpaired transfer leg read blank', () => {
    // No partner row, so no `transfer_id` — the register stopped reading it
    // for exactly this — and no counterpart: blank, where the register says
    // Transfer.
    expect(text({ needs_category: false, transfer_id: null })).toBe('Transfer')
  })

  it('DrillDownPanel: a tracking account leg read "Transfer"', () => {
    expect(text({ counterpart_account_id: 'a2' }, false)).toBe('—')
  })

  it('DrillDownPanel: a category it could not name read blank, not a dash', () => {
    expect(text({ category_id: 'gone' })).toBe('—')
  })

  it('MergePreviewModal: a row needing a category read "—", like a transfer', () => {
    expect(text({ needs_category: true })).not.toBe(text({ needs_category: false }))
  })

  it('LateArrivalsNote: a late transfer read "Needs a category"', () => {
    // It said so for every uncategorized row. The server now serves
    // `needs_category` on a late arrival, and a transfer's is false.
    expect(text({ category_id: null, needs_category: false })).toBe('Transfer')
    expect(text({ category_id: null, needs_category: true })).toBe('Needs Category')
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
