import { Info } from 'lucide-react'
import { usePendingReviewCount, usePendingReviewCountForAccount } from '../../api/transactions'
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

  if (!counts || (counts.unapproved === 0 && counts.uncategorized === 0)) {
    return null
  }

  const total = counts.unapproved + counts.uncategorized

  const parts: string[] = []
  if (counts.unapproved > 0) parts.push(`${counts.unapproved} unapproved`)
  if (counts.uncategorized > 0) parts.push(`${counts.uncategorized} uncategorized`)

  const message =
    total === 1
      ? `${parts.join(' and ')} transaction to review.`
      : `${parts.join(' and ')} transactions to review.`

  function handleView() {
    const filters: string[] = []
    if (counts!.unapproved > 0) filters.push('is: unapproved')
    if (counts!.uncategorized > 0) filters.push('is: uncategorized')
    onView(filters.join(' OR '))
  }

  return (
    <div className="pending-review-banner">
      <Info size={14} className="pending-review-banner__icon" />
      <span className="pending-review-banner__message">{message}</span>
      <button className="pending-review-banner__btn" onClick={handleView}>
        View
      </button>
    </div>
  )
}
