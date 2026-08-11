import { useNavigate } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { useAppStore } from '../../stores/appStore'
import { useActiveAIJobCount } from '../../api/aiJobs'
import './AIActivityBadge.css'

/**
 * Header pill showing how many AI jobs are queued/processing. Hidden when
 * AI is unconfigured or nothing is in flight; click jumps to the activity
 * log. The count polls faster while work is active.
 */
export function AIActivityBadge() {
  const navigate = useNavigate()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: count } = useActiveAIJobCount(budgetId)

  if (!count) return null

  return (
    <button
      className="ai-activity-badge"
      onClick={() => navigate('/ai-activity')}
      title={`${count} AI job${count !== 1 ? 's' : ''} processing — view activity`}
      aria-label={`${count} AI job${count !== 1 ? 's' : ''} processing`}
    >
      <Sparkles size={13} className="ai-activity-badge__icon" />
      <span>{count}</span>
    </button>
  )
}
