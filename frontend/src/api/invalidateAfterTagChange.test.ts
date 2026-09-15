/** Pins the list, so removing a key has to be deliberate. */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { invalidateAfterTagChange } from './invalidateAfterTagChange'
import { ROOT } from './queryKeys'

describe('invalidateAfterTagChange', () => {
  it('covers every cache a tag membership change stales — exactly', () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined)
    invalidateAfterTagChange(qc, 'b1')
    const got = spy.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey))
    const expected = [
      [ROOT.tags, 'b1'],
      [ROOT.tagSuggestions, 'b1'],
      [ROOT.categories, 'b1'],
      [ROOT.categoryClassification],
      [ROOT.budgetFilters, 'b1'],
      [ROOT.payees, 'b1'],
      [ROOT.reports],
      [ROOT.guide, 'b1'],
      [ROOT.guideSignals, 'b1'],
      [ROOT.guideCheckup, 'b1'],
      [ROOT.guideScenario],
      [ROOT.changes],
    ].map((k) => JSON.stringify(k))
    expect(new Set(got)).toEqual(new Set(expected))
    expect(got).toHaveLength(expected.length)
  })
})
