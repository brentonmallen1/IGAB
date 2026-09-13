import { useEffect, useRef, useState } from 'react'
import { useDeleteCategoryFlow } from '../../budget/DeleteCategoryModal/useDeleteCategoryFlow'
import { useFormatters } from '../../../hooks/useFormatters'
import type { WishEnvelope } from '../../../api/wishlist'
import { GuideDialog } from '../GuideDialog'

interface Props {
  budgetId: string
  wishName: string
  envelope: WishEnvelope
  onClose: () => void
}

/**
 * After a wish that owned its envelope is deleted: keep the envelope, or
 * delete it too through the ordinary category-delete flow — the one that
 * returns the money to To Be Assigned and can be undone. The wishlist never
 * deletes a category itself.
 */
export function DeleteWishDialog({ budgetId, wishName, envelope, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const [phase, setPhase] = useState<'ask' | 'deleting'>('ask')
  const { requestDelete, modal } = useDeleteCategoryFlow(budgetId, onClose)
  const sawModal = useRef(false)
  const available = envelope.available

  useEffect(() => {
    if (modal) sawModal.current = true
    // The flow's own dialog was dismissed without deleting: nothing left to show.
    else if (phase === 'deleting' && sawModal.current) onClose()
  }, [modal, phase, onClose])

  if (phase === 'deleting') return <>{modal}</>

  return (
    <GuideDialog
      title="Delete the envelope too?"
      onClose={onClose}
      historyKey="wishlist-delete-envelope"
      footer={
        <div className="dialog-actions">
          <button
            type="button"
            className="dialog-btn dialog-btn--danger"
            onClick={() => {
              setPhase('deleting')
              void requestDelete({
                kind: 'categories',
                ids: [envelope.category_id],
                name: envelope.name,
              })
            }}
          >
            Delete the envelope
          </button>
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--primary" onClick={onClose}>
              Keep the envelope
            </button>
          </div>
        </div>
      }
    >
      <div className="dialog__body wish-review">
        <p className="wish-review__done">
          <strong>{wishName}</strong> is off the list. Its envelope <strong>{envelope.name}</strong>{' '}
          is still in your budget
          {available > 0 ? ` holding ${formatMoney(available)}` : ''}. Delete it too? Any money in
          it goes back to To Be Assigned.
        </p>
      </div>
    </GuideDialog>
  )
}
