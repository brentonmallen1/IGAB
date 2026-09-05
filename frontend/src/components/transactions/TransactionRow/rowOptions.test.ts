/**
 * The two filters behind the register's pickers.
 *
 * Neither is cosmetic. A transfer payee picked as a payee names a transfer
 * the row is not; a non-categorizable envelope picked as a category is how a
 * card's set-aside swallowed money that then showed up nowhere in the budget.
 */
import { describe, expect, it } from 'vitest'
import { categoryOptions, payeeOptions } from './rowOptions'
import type { Category, CategoryGroup, Payee } from '../../../types'

const payees = [
  { id: 'p1', name: 'Nordstrom', transfer_account_id: null },
  { id: 'p2', name: 'Transfer : Sapphire Visa', transfer_account_id: 'a2' },
] as unknown as Payee[]

const groups = [{ id: 'g1', name: 'Everyday' }] as unknown as CategoryGroup[]
const categories = [
  { id: 'c1', name: 'Groceries', category_group_id: 'g1', is_categorizable: true },
  { id: 'c2', name: 'Sapphire Visa', category_group_id: 'g9', is_categorizable: false },
] as unknown as Category[]

describe('payeeOptions', () => {
  it('leaves out transfer payees — a destination is not a payee', () => {
    expect(payeeOptions(payees)).toEqual([{ id: 'p1', label: 'Nordstrom' }])
  })
})

describe('categoryOptions', () => {
  it('offers only what the server says may be filed to', () => {
    expect(categoryOptions(categories, groups)).toEqual([
      { id: 'c1', label: 'Groceries', group: 'Everyday' },
    ])
  })

  it('falls back to a blank heading when the group is not in the list', () => {
    // A hidden group resolves to no name; the option still has to render.
    const orphan = [{ ...categories[0], category_group_id: 'gone' }] as Category[]
    expect(categoryOptions(orphan, groups)[0].group).toBe('')
  })
})
