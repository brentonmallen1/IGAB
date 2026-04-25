import { X } from 'lucide-react'
import { useFillTargetsPreview, useFillTargetsApply } from '../../../api/budgets'
import { formatMoney } from '../../../utils/money'
import './AutoAssignModal.css'

interface Props {
  budgetId: string
  month: string
  onClose: () => void
}

export function AutoAssignModal({ budgetId, month, onClose }: Props) {
  const { data: preview, isLoading } = useFillTargetsPreview(budgetId, month, true)
  const apply = useFillTargetsApply(budgetId)

  async function handleApply() {
    if (!preview) return
    await apply.mutateAsync({ month, items: preview.items })
    onClose()
  }

  return (
    <div
      className="auto-assign-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="auto-assign-modal" role="dialog" aria-modal aria-labelledby="auto-assign-title">
        <div className="auto-assign-modal__header">
          <span id="auto-assign-title" className="auto-assign-modal__title">Auto-assign to targets</span>
          <button className="auto-assign-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="auto-assign-modal__body">
          {isLoading ? (
            <div className="auto-assign-modal__loading">Calculating…</div>
          ) : !preview || preview.items.length === 0 ? (
            <div className="auto-assign-modal__empty">
              {!preview ? 'No targets found.' : 'All targets are fully funded — nothing to assign.'}
            </div>
          ) : (
            <>
              <p className="auto-assign-modal__description">
                Available funds ({formatMoney(preview.tba_before)}) will be distributed
                proportionally to underfunded categories based on how much each needs.
              </p>
              <table className="auto-assign-modal__table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th className="auto-assign-modal__col-num">Current</th>
                    <th className="auto-assign-modal__col-num">Adding</th>
                    <th className="auto-assign-modal__col-num">New Total</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.map((item) => (
                    <tr key={item.category_id}>
                      <td>{item.category_name}</td>
                      <td className="auto-assign-modal__col-num">{formatMoney(item.current_assigned)}</td>
                      <td className="auto-assign-modal__col-num auto-assign-modal__addition">
                        +{formatMoney(item.proposed_addition)}
                      </td>
                      <td className="auto-assign-modal__col-num">{formatMoney(item.new_assigned)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>

        {preview && preview.items.length > 0 && (
          <div className="auto-assign-modal__footer">
            <div className="auto-assign-modal__tba-summary">
              <span className="auto-assign-modal__tba-label">TBA after:</span>
              <span className={`auto-assign-modal__tba-value ${preview.tba_after >= 0 ? 'positive' : 'negative'}`}>
                {formatMoney(preview.tba_after)}
              </span>
            </div>
            <div className="auto-assign-modal__actions">
              <button
                className="auto-assign-modal__btn auto-assign-modal__btn--secondary"
                onClick={onClose}
                disabled={apply.isPending}
              >
                Cancel
              </button>
              <button
                className="auto-assign-modal__btn auto-assign-modal__btn--primary"
                onClick={handleApply}
                disabled={apply.isPending}
              >
                {apply.isPending ? 'Applying…' : `Apply — ${formatMoney(preview.total_addition)}`}
              </button>
            </div>
          </div>
        )}

        {(!preview || preview.items.length === 0) && !isLoading && (
          <div className="auto-assign-modal__footer auto-assign-modal__footer--empty">
            <button className="auto-assign-modal__btn auto-assign-modal__btn--secondary" onClick={onClose}>
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
