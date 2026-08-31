import { useState } from 'react'
import { X } from 'lucide-react'
import {
  useCoverOverspentPreview,
  useCoverOverspentApply,
  useBudgetMonth,
} from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import './CoverOverspentModal.css'
import { useToastUndo } from '../../../utils/toastUndo'

interface Props {
  budgetId: string
  month: string
  onClose: () => void
}

export function CoverOverspentModal({ budgetId, month, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const { data: preview, isLoading, refetch } = useCoverOverspentPreview(budgetId, month, true)
  const apply = useCoverOverspentApply(budgetId)
  const showUndo = useToastUndo(budgetId)
  const [error, setError] = useState<string | null>(null)
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)

  // Which card carries the ridden red. Served on the card row (domain/cards.py
  // attributes it exactly), never re-derived here — the split is a running walk
  // per (category, card) the client has no way to reproduce.
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const riddenByCard = (budgetMonth?.cards ?? []).filter((c) => Number(c.overspent_this_month) > 0)

  const canApply = preview != null && preview.items.length > 0 && Number(preview.total_addition) > 0

  async function handleApply() {
    if (!preview) return
    setError(null)
    try {
      const result = await apply.mutateAsync({
        month,
        items: preview.items.map((i) => ({
          category_id: i.category_id,
          proposed_addition: i.proposed_addition,
        })),
      })
      showUndo(
        result.batch_id,
        `Covered ${formatMoney(Number(preview.total_addition))} of overspending across ${preview.items.length} ${preview.items.length === 1 ? 'category' : 'categories'}`
      )
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
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={trapRef}
        tabIndex={-1}
        className="cover-modal"
        role="dialog"
        aria-modal
        aria-labelledby="cover-modal-title"
      >
        <div className="cover-modal__header">
          <span id="cover-modal-title" className="cover-modal__title">
            Cover overspending
          </span>
          <button className="cover-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="cover-modal__body">
          {isLoading ? (
            <div className="cover-modal__loading">Calculating…</div>
          ) : !preview || preview.items.length === 0 ? (
            <div className="cover-modal__empty">
              {preview && Number(preview.total_overspent_credit) > 0 ? (
                <>
                  <p>Nothing here needs covering.</p>
                  <p className="cover-modal__on-cards">
                    This month&rsquo;s {formatMoney(preview.total_overspent_credit)} of overspending
                    was all spent on a card, so it rides there as debt instead of being covered from
                    Ready to Assign. Pay it down by assigning to the card.
                  </p>
                </>
              ) : (
                'Nothing is overspent this month.'
              )}
            </div>
          ) : (
            <>
              <p className="cover-modal__description">
                Ready to Assign ({formatMoney(preview.tba_before)}) will cover overspent categories
                — in full when it stretches, proportionally when it doesn't.
              </p>
              {/* The grid's red is larger than this table, on purpose. Saying so
                  here is cheaper than letting someone find the gap and stop
                  trusting both numbers. */}
              {Number(preview.total_overspent_credit) > 0 && (
                <>
                  <p className="cover-modal__on-cards">
                    A further {formatMoney(preview.total_overspent_credit)} was spent on a card.
                    That rides on the card as debt, never charges Ready to Assign, and is not listed
                    here — assigning cash to it would not retire it. Pay it down by assigning to the
                    card.
                  </p>
                  {/* Only worth naming with more than one card: with a single
                      card this list restates the sentence above it. Cards are
                      paid separately, so which one carries the red is a real
                      question once there are two. */}
                  {riddenByCard.length > 1 && (
                    <ul className="cover-modal__on-cards-list">
                      {riddenByCard.map((c) => (
                        <li key={c.account_id}>
                          {c.name}: {formatMoney(c.overspent_this_month)}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              <table className="cover-modal__table">
                <caption className="sr-only">Overspent categories and proposed coverage</caption>
                <thead>
                  <tr>
                    <th scope="col">Category</th>
                    <th scope="col" className="cover-modal__col-num">
                      Overspent
                    </th>
                    <th scope="col" className="cover-modal__col-num">
                      Covering
                    </th>
                    <th scope="col" className="cover-modal__col-num">
                      Remaining
                    </th>
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
              <span
                className={`cover-modal__tba-value ${Number(preview.tba_after) >= 0 ? 'positive' : 'negative'}`}
              >
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
