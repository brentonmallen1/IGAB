/**
 * A dropped cache key is invisible: the screen just shows a number that was
 * true a minute ago. This pins the list so removing one has to be deliberate.
 *
 * It is not hypothetical — `invalidateAfterUndo` shipped
 * `['category-groups', budgetId]` against a query registered as
 * `['categoryGroups', budgetId]`, so undoing a category-group change refreshed
 * nothing at all until it was found by reading.
 */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { invalidateAfterCategoryChange } from './invalidateAfterCategoryChange'

function keysInvalidatedFor(budgetId: string | null): string[] {
  const qc = new QueryClient()
  const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined)
  invalidateAfterCategoryChange(qc, budgetId)
  return spy.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey))
}

describe('invalidateAfterCategoryChange', () => {
  it('covers every cache a category delete stales', () => {
    const keys = keysInvalidatedFor('b1')

    // The grid and the money on it.
    expect(keys).toContain(JSON.stringify(['categories']))
    expect(keys).toContain(JSON.stringify(['categoryGroups']))
    expect(keys).toContain(JSON.stringify(['budgetMonth', 'b1']))

    // The register's category column, and the rows that just changed.
    expect(keys).toContain(JSON.stringify(['transactions']))
    expect(keys).toContain(JSON.stringify(['all-transactions']))
    expect(keys).toContain(JSON.stringify(['category-transactions']))

    // The needs-a-category badge counts exactly the rows a delete creates.
    expect(keys).toContain(JSON.stringify(['pending-review-count']))

    // Payee defaults and scheduled categories are cleared by the delete.
    expect(keys).toContain(JSON.stringify(['payees']))
    expect(keys).toContain(JSON.stringify(['scheduled-transactions']))

    // Views and filters lose their placements and selections.
    expect(keys).toContain(JSON.stringify(['budgetViews']))
    expect(keys).toContain(JSON.stringify(['budgetFilters']))

    // Reports group by category.
    expect(keys).toContain(JSON.stringify(['reports']))
  })

  it('spells the group key the way the query registers it', () => {
    // `categoryGroups`, not `category-groups`. The wrong spelling is not an
    // error anywhere — it silently matches no query.
    const keys = keysInvalidatedFor('b1')
    expect(keys).toContain(JSON.stringify(['categoryGroups']))
    expect(keys).not.toContain(JSON.stringify(['category-groups']))
  })

  it('falls back to every budget month when no budget is given', () => {
    expect(keysInvalidatedFor(null)).toContain(JSON.stringify(['budgetMonth']))
  })
})
