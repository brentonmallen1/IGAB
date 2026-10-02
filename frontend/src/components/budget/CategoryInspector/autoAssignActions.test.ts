import { describe, expect, it } from 'vitest'
import { autoAssignRows } from './autoAssignActions'
import type { CategoryBalance, CategoryHistory } from '../../../types'

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
})
