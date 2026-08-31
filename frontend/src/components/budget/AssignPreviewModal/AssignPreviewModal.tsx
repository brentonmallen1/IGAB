import { X } from 'lucide-react'
import { useToastUndo } from '../../../utils/toastUndo'
import { useAssignApply, useAssignPreview } from '../../../api/assign'
import { useFormatters } from '../../../hooks/useFormatters'
import type { AssignStrategy } from '../../../types'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { STRATEGY_META } from '../AssignDropdown/strategyMeta'
import './AssignPreviewModal.css'

interface Props {
  budgetId: string
  month: string
  strategy: AssignStrategy
  onClose: () => void
}

/**
 * Per-category preview for a bulk assign strategy: current → new with a
 * signed change column, TBA before/after, and an explicit warning when the
 * apply would push TBA negative. Apply recomputes server-side; the toast
 * reports what actually happened.
 */
export function AssignPreviewModal({ budgetId, month, strategy, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const { data: preview, isLoading } = useAssignPreview(budgetId, month, strategy)
  const apply = useAssignApply(budgetId)
  const showUndo = useToastUndo(budgetId)
  const meta = STRATEGY_META[strategy]
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)

  const tbaAfter = Number(preview?.tba_after ?? 0)
  const toAssign = Number(preview?.to_assign ?? 0)
  const toReturn = Number(preview?.to_return ?? 0)
  const hasChanges = preview?.items.some((i) => i.delta !== 0) ?? false

  async function handleApply() {
    if (!preview) return
    const result = await apply.mutateAsync({ month, strategy })
    const assigned = result.to_assign
    const returned = result.to_return
    const parts = []
    if (assigned > 0) parts.push(`${formatMoney(assigned)} assigned`)
    if (returned > 0) parts.push(`${formatMoney(returned)} returned to TBA`)
    showUndo(
      result.categories_changed > 0 ? result.batch_id : null,
      parts.length > 0
        ? `${meta.label}: ${parts.join(', ')} across ${result.categories_changed} categories`
        : `${meta.label}: nothing to change`
    )
    onClose()
  }

  return (
    <div
      className="assign-preview-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={trapRef}
        tabIndex={-1}
        className="assign-preview-modal"
        role="dialog"
        aria-modal
        aria-labelledby="assign-preview-title"
      >
        <div className="assign-preview-modal__header">
          <span id="assign-preview-title" className="assign-preview-modal__title">
            {meta.label}
          </span>
          <button className="assign-preview-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="assign-preview-modal__body">
          {isLoading ? (
            <div className="assign-preview-modal__loading">Calculating…</div>
          ) : !preview || preview.items.length === 0 ? (
            <div className="assign-preview-modal__empty">Nothing to change — you're all set.</div>
          ) : (
            <>
              <p className="assign-preview-modal__description">{meta.description}</p>
              <table className="assign-preview-modal__table">
                <caption className="sr-only">Per-category changes for {meta.label}</caption>
                <thead>
                  <tr>
                    <th scope="col">Category</th>
                    <th scope="col" className="assign-preview-modal__col-num">
                      Current
                    </th>
                    <th scope="col" className="assign-preview-modal__col-num">
                      Change
                    </th>
                    <th scope="col" className="assign-preview-modal__col-num">
                      New Total
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.map((item) => {
                    const delta = item.delta
                    return (
                      <tr key={item.category_id}>
                        <td>{item.category_name}</td>
                        <td className="assign-preview-modal__col-num">
                          {formatMoney(item.current_assigned)}
                        </td>
                        <td
                          className={`assign-preview-modal__col-num ${
                            delta > 0
                              ? 'assign-preview-modal__delta--positive'
                              : delta < 0
                                ? 'assign-preview-modal__delta--negative'
                                : ''
                          }`}
                        >
                          {delta > 0 ? '+' : ''}
                          {formatMoney(delta)}
                        </td>
                        <td className="assign-preview-modal__col-num">
                          {formatMoney(item.new_assigned)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {tbaAfter < 0 && (
                <div className="assign-preview-modal__overassign-warning">
                  This assigns more than you have — Ready to Assign will go negative (
                  {formatMoney(tbaAfter)}). You can cover it later by moving money back.
                </div>
              )}
            </>
          )}
        </div>

        {preview && preview.items.length > 0 && (
          <div className="assign-preview-modal__footer">
            <div className="assign-preview-modal__tba-summary">
              <span className="assign-preview-modal__tba-label">TBA:</span>
              <span className="assign-preview-modal__tba-value">
                {formatMoney(preview.tba_before)}
              </span>
              <span className="assign-preview-modal__tba-arrow">→</span>
              <span
                className={`assign-preview-modal__tba-value ${
                  tbaAfter >= 0 ? 'positive' : 'negative'
                }`}
              >
                {formatMoney(tbaAfter)}
              </span>
            </div>
            <div className="assign-preview-modal__actions">
              <button
                className="assign-preview-modal__btn assign-preview-modal__btn--secondary"
                onClick={onClose}
                disabled={apply.isPending}
              >
                Cancel
              </button>
              <button
                className="assign-preview-modal__btn assign-preview-modal__btn--primary"
                onClick={handleApply}
                disabled={apply.isPending || !hasChanges}
              >
                {apply.isPending
                  ? 'Applying…'
                  : toAssign > 0 && toReturn > 0
                    ? `Apply — ${formatMoney(toAssign)} in, ${formatMoney(toReturn)} back`
                    : toReturn > 0
                      ? `Apply — return ${formatMoney(toReturn)}`
                      : `Apply — ${formatMoney(toAssign)}`}
              </button>
            </div>
          </div>
        )}

        {(!preview || preview.items.length === 0) && !isLoading && (
          <div className="assign-preview-modal__footer assign-preview-modal__footer--empty">
            <button
              className="assign-preview-modal__btn assign-preview-modal__btn--secondary"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
