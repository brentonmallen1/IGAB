import { describe, expect, it } from 'vitest'
import { autoAssignAmounts, autoAssignCategoryIds, autoAssignRows } from './autoAssignActions'
import type { CategoryBalance, CategoryHistory } from '../../../types'
import { makeCategory } from '../../../test-utils/factories'

const balance = (category_id: string, target_assigned: number | null) =>
  ({ category_id, target_assigned }) as unknown as CategoryBalance

const history = (category_id: string, last: number) =>
  ({
    category_id,
    last_month_assigned: last,
    last_month_spent: 0,
    average_assigned: 0,
    average_spent: 0,
  }) as unknown as CategoryHistory

describe('autoAssignRows', () => {
  it('leads with Target Amount, summing the served figure of the selected targets only', () => {
    const rows = autoAssignRows(
      ['groceries', 'dining', 'fun'],
      [],
      [
        balance('groceries', 500),
        balance('dining', 100),
        balance('fun', null),
        balance('rent', 900),
      ]
    )
    expect(rows[0]).toEqual({ action: 'target_amount', label: 'Target Amount', value: 600 })
  })

  it('offers no Target Amount when nothing selected has a target', () => {
    const rows = autoAssignRows(['fun'], [], [balance('fun', null), balance('rent', 900)])
    expect(rows.map((r) => r.action)).not.toContain('target_amount')
  })

  it('sums history across the selection, as both panels used to separately', () => {
    const rows = autoAssignRows(['a', 'b'], [history('a', 30), history('b', 12.5)], undefined)
    expect(rows.find((r) => r.action === 'last_month_assigned')?.value).toBe(42.5)
    expect(rows.map((r) => r.action)).toEqual([
      'last_month_assigned',
      'last_month_spent',
      'average_assigned',
      'average_spent',
    ])
  })

  it('is the sum of the very figures a press applies, so the button says what it sets', () => {
    const ids = ['a', 'b']
    const histories = [history('a', 30), history('b', 12.5)]
    const balances = [balance('a', 70), balance('b', null)]
    for (const row of autoAssignRows(ids, histories, balances)) {
      const amounts = autoAssignAmounts(row.action, ids, histories, balances)!
      expect([...amounts.values()].reduce((s, v) => s + v, 0)).toBe(row.value)
    }
  })
})

describe('autoAssignAmounts', () => {
  it('sets each selected envelope to its own history figure', () => {
    const amounts = autoAssignAmounts(
      'last_month_assigned',
      ['a', 'b'],
      [history('a', 30), history('b', 12.5), history('other', 99)],
      undefined
    )
    expect(amounts).toEqual(
      new Map([
        ['a', 30],
        ['b', 12.5],
      ])
    )
  })

  it('leaves an envelope without a target out of Target Amount', () => {
    const amounts = autoAssignAmounts('target_amount', ['a', 'b'], undefined, [
      balance('a', 70),
      balance('b', null),
    ])
    expect(amounts).toEqual(new Map([['a', 70]]))
  })

  it('zeroes every selected envelope on Reset, history or not', () => {
    expect(autoAssignAmounts('reset', ['a', 'b'], undefined, undefined)).toEqual(
      new Map([
        ['a', 0],
        ['b', 0],
      ])
    )
  })

  it('knows nothing until the history has loaded — an unknown figure is not zero', () => {
    expect(autoAssignAmounts('average_spent', ['a'], undefined, [])).toBeNull()
  })
})

describe('autoAssignCategoryIds', () => {
  it('acts on the envelopes money may enter — never Income, never an archived group', () => {
    // The month summary sent every listed category, Income included, and the
    // server refuses a press that names income: the whole button failed.
    const ids = autoAssignCategoryIds([
      makeCategory({ id: 'groceries' }),
      makeCategory({ id: 'paycheck', is_fundable: false, is_assignable: false }),
      makeCategory({ id: 'in-archived-group', is_fundable: false }),
      // A card's envelope is never offered in a picker, but it is funded.
      makeCategory({ id: 'card', is_assignable: false, is_fundable: true }),
    ])
    expect(ids).toEqual(['groceries', 'card'])
  })
})
