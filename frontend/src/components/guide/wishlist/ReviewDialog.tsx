import { useState } from 'react'
import { useAffirmWish, useUpdateWish, type Wish } from '../../../api/wishlist'
import { useFormatters } from '../../../hooks/useFormatters'
import { GuideDialog } from '../GuideDialog'
import { fundingLabel, reachLabel } from './wishlistCopy'

interface Props {
  budgetId: string
  due: Wish[]
  reviewDays: number
  onClose: () => void
}

/**
 * "Still want this?" — one wish at a time, for those not affirmed in a while.
 *
 * Opened from a line on the tab and nowhere else: the wishlist never sends a
 * notification. The list is snapshotted on open so answering one does not
 * reshuffle the rest under the reader.
 */
export function ReviewDialog({ budgetId, due, reviewDays, onClose }: Props) {
  const [queue] = useState(() => due)
  const [index, setIndex] = useState(0)
  const affirm = useAffirmWish(budgetId)
  const update = useUpdateWish(budgetId)
  const fmt = useFormatters()
  const current = queue[index]
  const pending = affirm.isPending || update.isPending
  const next = () => setIndex((i) => i + 1)

  return (
    <GuideDialog title="Still want these?" onClose={onClose} historyKey="wishlist-review">
      <div className="guide-dialog__body wish-review">
        {current ? (
          <>
            <p className="wish-review__progress">
              {index + 1} of {queue.length}
            </p>
            <div className="wish-review__card">
              <h4 className="wish-review__name">{current.name}</h4>
              <p className="wish-review__meta">
                {fmt.formatMoney(Number(current.cost))} · {fundingLabel(current)} ·{' '}
                {reachLabel(current, fmt)}
              </p>
              <p className="wish-review__added">
                Added {fmt.formatDate(current.created_at.slice(0, 10))}
                {current.last_affirmed_at &&
                  `, last affirmed ${fmt.formatDate(current.last_affirmed_at.slice(0, 10))}`}
              </p>
            </div>
            <div className="wish-review__actions">
              <button
                type="button"
                className="guide-checkup__run"
                disabled={pending}
                onClick={() => affirm.mutate(current.id, { onSuccess: next })}
              >
                Still want it
              </button>
              <button
                type="button"
                className="guide-link-button"
                disabled={pending}
                onClick={() => update.mutate({ id: current.id, status: 'dropped' }, { onSuccess: next })}
              >
                Drop it
              </button>
              <button
                type="button"
                className="guide-link-button"
                disabled={pending}
                onClick={() => update.mutate({ id: current.id, status: 'done' }, { onSuccess: next })}
              >
                Done — got it
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="wish-review__done">
              That’s everyone. Next review in {reviewDays} days.
            </p>
            <div className="wish-review__actions">
              <button type="button" className="guide-checkup__run" onClick={onClose}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </GuideDialog>
  )
}
