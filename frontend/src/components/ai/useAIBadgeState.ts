import { useAppStore } from '../../stores/appStore'
import { useAIJobCounts } from '../../api/aiJobs'
import { aiBadgeState, type AIBadgeState } from './aiBadge'

/**
 * The AI badge's state for whoever is drawing it — the sidebar, the More
 * sheet, and the mobile More button, which has to know whether anything
 * behind it is asking for attention.
 *
 * Its own file so `AIActivityNavBadge.tsx` exports only a component (fast
 * refresh), and so the three callers share one reading of the counts.
 */
export function useAIBadgeState(): AIBadgeState {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data } = useAIJobCounts(budgetId)
  return aiBadgeState({ active: data?.active ?? 0, needsReview: data?.needsReview ?? 0 })
}
