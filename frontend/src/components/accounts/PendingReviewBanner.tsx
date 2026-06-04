import { Info } from 'lucide-react'
import { usePendingReviewCount, usePendingReviewCountForAccount } from '../../api/transactions'
import { Tooltip } from '../common/Tooltip/Tooltip'
import './PendingReviewBanner.css'

interface Props {
  budgetId: string
  accountId?: string
  onView: (search: string) => void
}

export function PendingReviewBanner({ budgetId, accountId, onView }: Props) {
  const budgetCounts = usePendingReviewCount(accountId ? null : budgetId)
  const accountCounts = usePendingReviewCountForAccount(accountId ?? null)
  const counts = accountId ? accountCounts.data : budgetCounts.data

  const total = counts?.total ?? (counts ? counts.unapproved + counts.uncategorized : 0)

  if (!counts || total === 0) {
    return null
  }

  const tooltipLines: string[] = []
  if (counts.unapproved_only > 0) tooltipLines.push(`${counts.unapproved_only} unapproved`)
  if (counts.uncategorized_only > 0) tooltipLines.push(`${counts.uncategorized_only} need category`)
  if (counts.both > 0) tooltipLines.push(`${counts.both} unapproved + need category`)

  const tooltipContent =
    tooltipLines.length > 0 ? (
      <>
        {tooltipLines.map((line) => (
          <div key={line}>{line}</div>
        ))}
      </>
    ) : null

  const message = total === 1 ? '1 transaction to review.' : `${total} transactions to review.`

  function handleView() {
    onView('is: unapproved OR is: uncategorized NOT is: pending')
  }

  return (
    <div className="pending-review-banner">
      <Tooltip content={tooltipContent}>
        <span className="pending-review-banner__message">
          <Info size={14} className="pending-review-banner__icon" />
          {message}
        </span>
      </Tooltip>
      <button className="pending-review-banner__btn" onClick={handleView}>
        View
      </button>
    </div>
  )
}
