import { useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import { useAIJobCounts } from '../../api/aiJobs'
import './AIActivityBadge.css'

/**
 * Header pill for AI work. It shows one of two things:
 *
 * - work in flight (queued/processing), pulsing, linking to the activity log;
 * - otherwise, transactions the AI created that are still waiting for review,
 *   steady, linking to the register filtered to them.
 *
 * The second state is the point. The badge used to count only in-flight jobs,
 * so it vanished the instant a receipt finished — the one moment the user
 * actually needed to be told something had arrived.
 */
export function AIActivityBadge() {
  const navigate = useNavigate()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data } = useAIJobCounts(budgetId)

  const active = data?.active ?? 0
  const needsReview = data?.needsReview ?? 0
  if (!active && !needsReview) return null

  // In-flight work wins the badge: it's transient, and the review count will
  // still be there once it settles.
  const processing = active > 0
  const count = processing ? active : needsReview
  const label = processing
    ? `${active} AI job${active !== 1 ? 's' : ''} processing — view activity`
    : `${needsReview} AI transaction${needsReview !== 1 ? 's' : ''} to review`

  return (
    <button
      className={`ai-activity-badge ${processing ? '' : 'ai-activity-badge--review'}`}
      onClick={() => navigate(processing ? '/ai-activity' : '/transactions?q=is%3A+unapproved')}
      title={label}
      aria-label={label}
    >
      <Sparkles size={13} className="ai-activity-badge__icon" />
      <span>{count}</span>
    </button>
  )
}
