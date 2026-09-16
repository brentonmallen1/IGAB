import type { QueryClient } from '@tanstack/react-query'
import { ROOT } from './queryKeys'

/**
 * Every cache a change to which categories carry a tag (or a category's
 * savings mode) can stale.
 *
 * Tags are a classification override: they move the "Counts as" badge, a
 * filter that names a tag, every report built from a tag (savings rate,
 * essentials, emergency coverage, subscriptions), and the Guide's signals,
 * checkup and calculators that read those reports. The tag list itself
 * carries the counts. One list, for the reason `invalidateAfterCategoryChange`
 * gives: the copies drift, and a dropped key is invisible.
 */
export function invalidateAfterTagChange(qc: QueryClient, budgetId: string | null): Promise<void> {
  const roots = [
    [ROOT.tags, budgetId],
    [ROOT.tagSuggestions, budgetId],
    [ROOT.categories, budgetId],
    // Its key is not under ['categories'].
    [ROOT.categoryClassification],
    [ROOT.budgetFilters, budgetId],
    [ROOT.payees, budgetId],
    [ROOT.reports],
    [ROOT.guide, budgetId],
    [ROOT.guideSignals, budgetId],
    [ROOT.guideCheckup, budgetId],
    [ROOT.guideScenario],
    [ROOT.emergencyFund, budgetId],
    [ROOT.changes],
  ]
  return Promise.all(roots.map((queryKey) => qc.invalidateQueries({ queryKey }))).then(
    () => undefined
  )
}
