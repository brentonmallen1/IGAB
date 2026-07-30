import { useState } from 'react'
import { X } from 'lucide-react'
import { useCoverOverspentPreview, useCoverOverspentApply } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import './CoverOverspentModal.css'

interface Props {
  budgetId: string
  month: string
  onClose: () => void
}

export function CoverOverspentModal({ budgetId, month, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const { data: preview, isLoading, refetch } = useCoverOverspentPreview(budgetId, month, true)
  const apply = useCoverOverspentApply(budgetId)
  const [error, setError] = useState<string | null>(null)
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)

  const canApply = preview != null && preview.items.length > 0 && Number(preview.total_addition) > 0

  async function handleApply() {
    if (!preview) return
    setError(null)
    try {
      await apply.mutateAsync({
        month,
        items: preview.items.map((i) => ({
          category_id: i.category_id,
          proposed_addition: i.proposed_addition,
        })),
      })
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Cover failed')
      refetch()
    }
  }

  return (
    <div
      className="cover-modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div ref={trapRef} tabIndex={-1} className="cover-modal" role="dialog" aria-modal aria-labelledby="cover-modal-title">
        <div className="cover-modal__header">
          <span id="cover-modal-title" className="cover-modal__title">Cover overspending</span>
          <button className="cover-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="cover-modal__body">
          {isLoading ? (
            <div className="cover-modal__loading">Calculating…</div>
          ) : !preview || preview.items.length === 0 ? (
            <div className="cover-modal__empty">Nothing is overspent this month.</div>
          ) : (
            <>
              <p className="cover-modal__description">
                Ready to Assign ({formatMoney(preview.tba_before)}) will cover overspent
                categories — in full when it stretches, proportionally when it doesn't.
              </p>
              <table className="cover-modal__table">
                <caption className="sr-only">Overspent categories and proposed coverage</caption>
                <thead>
                  <tr>
                    <th scope="col">Category</th>
                    <th scope="col" className="cover-modal__col-num">Overspent</th>
                    <th scope="col" className="cover-modal__col-num">Covering</th>
                    <th scope="col" className="cover-modal__col-num">Remaining</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.map((item) => (
                    <tr key={item.category_id}>
                      <td>{item.category_name}</td>
                      <td className="cover-modal__col-num cover-modal__overspent">
                        {formatMoney(-item.overspent)}
                      </td>
                      <td className="cover-modal__col-num cover-modal__covering">
                        +{formatMoney(item.proposed_addition)}
                      </td>
                      <td className="cover-modal__col-num">
                        {Number(item.remaining_after) > 0
                          ? formatMoney(-item.remaining_after)
                          : formatMoney(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {Number(preview.total_addition) <= 0 && (
                <p className="cover-modal__no-funds">
                  Ready to Assign is empty — add or move money there first.
                </p>
              )}
            </>
          )}
          {error && <div className="cover-modal__error">{error}</div>}
        </div>

        {preview && preview.items.length > 0 ? (
          <div className="cover-modal__footer">
            <div className="cover-modal__tba-summary">
              <span className="cover-modal__tba-label">TBA after:</span>
              <span className={`cover-modal__tba-value ${Number(preview.tba_after) >= 0 ? 'positive' : 'negative'}`}>
                {formatMoney(preview.tba_after)}
              </span>
            </div>
            <div className="cover-modal__actions">
              <button
                className="cover-modal__btn cover-modal__btn--secondary"
                onClick={onClose}
                disabled={apply.isPending}
              >
                Cancel
              </button>
              <button
                className="cover-modal__btn cover-modal__btn--primary"
                onClick={handleApply}
                disabled={apply.isPending || !canApply}
              >
                {apply.isPending ? 'Covering…' : `Cover — ${formatMoney(preview.total_addition)}`}
              </button>
            </div>
          </div>
        ) : (
          !isLoading && (
            <div className="cover-modal__footer cover-modal__footer--empty">
              <button className="cover-modal__btn cover-modal__btn--secondary" onClick={onClose}>
                Close
              </button>
            </div>
          )
        )}
      </div>
    </div>
  )
}
