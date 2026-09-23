import { useState } from 'react'
import { useAffirmWish, type Wish } from '../../../api/wishlist'
import { useFormatters } from '../../../hooks/useFormatters'
import { GuideDialog } from '../GuideDialog'
import { fundingLabel, reachLabel } from './wishlistCopy'

interface Props {
  budgetId: string
  due: Wish[]
  reviewDays: number
  /** End a wish. The panel's, not this dialog's: ending one may leave an
   *  envelope standing, and that question is asked in one place. Answering
   *  it while this queue is still open would stack dialogs, so the panel
   *  holds the prompt until the review closes. */
  onEnd: (wish: Wish, status: 'done' | 'dropped') => Promise<void>
  onClose: () => void
}

/**
 * "Still want this?" — one wish at a time, for those not affirmed in a while.
 *
 * Opened from a line on the tab and nowhere else: the wishlist never sends a
 * notification. The list is snapshotted on open so answering one does not
 * reshuffle the rest under the reader.
 */
export function ReviewDialog({ budgetId, due, reviewDays, onEnd, onClose }: Props) {
  const [queue] = useState(() => due)
  const [index, setIndex] = useState(0)
  const [ending, setEnding] = useState(false)
  const affirm = useAffirmWish(budgetId)
  const fmt = useFormatters()
  const current = queue[index]
  const pending = affirm.isPending || ending
  const next = () => setIndex((i) => i + 1)

  async function end(wish: Wish, status: 'done' | 'dropped') {
    setEnding(true)
    try {
      await onEnd(wish, status)
      next()
    } finally {
      setEnding(false)
    }
  }

  return (
    <GuideDialog
      title="Still want these?"
      onClose={onClose}
      historyKey="wishlist-review"
      footer={
        <div className="dialog-actions">
          {current ? (
            <>
              <button
                type="button"
                className="dialog-btn dialog-btn--secondary"
                disabled={pending}
                onClick={() => void end(current, 'dropped')}
              >
                Drop it
              </button>
              <div className="dialog-actions__end">
                <button
                  type="button"
                  className="dialog-btn dialog-btn--secondary"
                  disabled={pending}
                  onClick={() => void end(current, 'done')}
                >
                  Done — got it
                </button>
                <button
                  type="button"
                  className="dialog-btn dialog-btn--primary"
                  disabled={pending}
                  onClick={() => affirm.mutate(current.id, { onSuccess: next })}
                >
                  Still want it
                </button>
              </div>
            </>
          ) : (
            <div className="dialog-actions__end">
              <button type="button" className="dialog-btn dialog-btn--primary" onClick={onClose}>
                Close
              </button>
            </div>
          )}
        </div>
      }
    >
      <div className="dialog__body wish-review">
        {current ? (
          <>
            <p className="wish-review__progress">
              {index + 1} of {queue.length}
            </p>
            <div className="wish-review__card">
              <h4 className="wish-review__name">{current.name}</h4>
              <p className="wish-review__meta">
                {fmt.formatMoney(current.cost)} · {fundingLabel(current)} ·{' '}
                {reachLabel(current, fmt)}
              </p>
              <p className="wish-review__added">
                {/* `added_on`, not the instant: the day the person added it
                    is served precisely because slicing `created_at` gives the
                    UTC day, which is tomorrow's every evening west of UTC. */}
                Added {fmt.formatDate(current.added_on)}
                {current.affirmed_on && `, last affirmed ${fmt.formatDate(current.affirmed_on)}`}
              </p>
            </div>
          </>
        ) : (
          <p className="wish-review__done">That’s everyone. Next review in {reviewDays} days.</p>
        )}
      </div>
    </GuideDialog>
  )
}
