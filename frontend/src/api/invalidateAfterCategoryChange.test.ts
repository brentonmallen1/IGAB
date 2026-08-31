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
import { ROOT } from './queryKeys'

function keysInvalidatedFor(budgetId: string | null): string[] {
  const qc = new QueryClient()
  const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined)
  invalidateAfterCategoryChange(qc, budgetId)
  return spy.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey))
}

describe('invalidateAfterCategoryChange', () => {
  it('covers every cache a category delete stales — the whole list, exactly', () => {
    // Set equality, not toContain: a partial pin let five keys drop without
    // failing anything (found in review). Removing OR adding a key now has
    // to happen here too, deliberately.
    const expected = [
      [ROOT.categories],
      [ROOT.categoryGroups],
      [ROOT.archivedCategories],
      [ROOT.categoryClassification],
      ['budgetMonth', 'b1'],
      [ROOT.transactions],
      [ROOT.allTransactions],
      [ROOT.budgetTransactions],
      [ROOT.transactionsPeek],
      [ROOT.payeeTransactions],
      [ROOT.pendingReviewCount],
      [ROOT.pendingReviewCountAccount],
      [ROOT.payees],
      [ROOT.scheduledTransactions],
      [ROOT.budgetViews],
      [ROOT.budgetFilters],
      [ROOT.reports],
      [ROOT.changes],
    ].map((k) => JSON.stringify(k))

    expect(keysInvalidatedFor('b1').sort()).toEqual(expected.sort())
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
