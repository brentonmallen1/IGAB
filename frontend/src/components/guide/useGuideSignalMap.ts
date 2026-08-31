import { useMemo } from 'react'
import { useAppStore } from '../../stores/appStore'
import { useGuideOverview, useGuideSignals, type ConceptInfo, type Signal } from '../../api/guide'
import type { SignalKey } from '../../content/roadmap'

/**
 * Signals and concepts keyed for lookup by a roadmap node.
 *
 * One fetch for the whole roadmap rather than one per node — every view
 * renders many nodes, and the signals endpoint answers for all of them at
 * once. `enabled` follows the personalisation preference so switching it off
 * really does stop the request.
 */
export function useGuideSignalMap() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  const personalization = overview?.preferences.personalization ?? true
  const { data, isLoading } = useGuideSignals(budgetId, personalization)

  return useMemo(() => {
    const signals = new Map<SignalKey, Signal>()
    for (const s of data?.concepts ?? []) signals.set(s.key, s)
    const concepts = new Map<SignalKey, ConceptInfo>()
    for (const c of overview?.concepts ?? []) concepts.set(c.key, c)
    return {
      budgetId,
      signals,
      concepts,
      personalization: data?.personalization ?? personalization,
      progress: overview?.progress ?? {},
      isLoading,
    }
  }, [data, overview, personalization, budgetId, isLoading])
}
