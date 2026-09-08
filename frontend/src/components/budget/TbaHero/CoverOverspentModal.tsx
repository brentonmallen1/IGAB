import { useState } from 'react'
import {
  useCoverOverspentPreview,
  useCoverOverspentApply,
  useBudgetMonth,
} from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { Dialog } from '../../common/Dialog/Dialog'
import './CoverOverspentModal.css'
import { useUndoToast } from '../../../utils/toastUndo'

interface Props {
  budgetId: string
  month: string
  onClose: () => void
}

export function CoverOverspentModal({ budgetId, month, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const { data: preview, isLoading, refetch } = useCoverOverspentPreview(budgetId, month, true)
  const apply = useCoverOverspentApply(budgetId)
  const notify = useUndoToast()
  const [error, setError] = useState<string | null>(null)
  // Which card carries the ridden red. Served on the card row (domain/cards.py
  // attributes it exactly), never re-derived here — the split is a running walk
  // per (category, card) the client has no way to reproduce.
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const riddenByCard = (budgetMonth?.cards ?? []).filter((c) => c.overspent_this_month > 0)

  const canApply = preview != null && preview.items.length > 0 && preview.total_addition > 0

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
      notify(
        `Covered ${formatMoney(preview.total_addition)} of overspending across ${preview.items.length} ${preview.items.length === 1 ? 'category' : 'categories'}`,
        result.batch_id ? { batch: result.batch_id } : null
      )
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Cover failed')
      refetch()
    }
  }

  // Dialog pins the footer below the scroll region; which of the two it is
  // depends on whether anything actually needs covering.
  const footer =
    preview && preview.items.length > 0 ? (
      <>
        <div className="cover-modal__tba-summary">
          <span className="cover-modal__tba-label">TBA after:</span>
          <span
            className={`cover-modal__tba-value ${preview.tba_after >= 0 ? 'positive' : 'negative'}`}
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
      </>
    ) : !isLoading ? (
      <button className="cover-modal__btn cover-modal__btn--secondary" onClick={onClose}>
        Close
      </button>
    ) : undefined

  return (
    <Dialog
      title="Cover overspending"
      onClose={onClose}
      historyKey="cover-overspent"
      className="cover-modal"
      footer={footer}
    >
      <div className="cover-modal__body">
        {isLoading ? (
          <div className="cover-modal__loading">Calculating…</div>
        ) : !preview || preview.items.length === 0 ? (
          <div className="cover-modal__empty">Nothing is overspent this month.</div>
        ) : (
          <>
            <p className="cover-modal__description">
              Ready to Assign ({formatMoney(preview.tba_before)}) will cover these envelopes — in
              full when it stretches, proportionally when it doesn&rsquo;t.
            </p>
            {/* Where part of this money goes. Covering a ride is not a
                  different amount, it is a different destination: into the
                  card's set-aside, retiring debt, rather than into the
                  envelope to spend. Said once here, and per row below. */}
            {preview.total_overspent_credit > 0 && (
              <>
                <p className="cover-modal__on-cards">
                  {formatMoney(preview.total_overspent_credit)} of this was swiped on a card. That
                  part is covered too — it moves into the card&rsquo;s set-aside and retires the
                  debt riding there, instead of staying in the envelope to spend.
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
                  {/* "Still red", not "remaining cash short": the column has
                      to answer the question the grid asks, or a row can read
                      $0.00 beside a cell that is still in the red. */}
                  <th scope="col" className="cover-modal__col-num">
                    Still red
                  </th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((item) => {
                  // What the grid will still show after this cover: the cash
                  // this dialog could not reach, plus the part that rode onto
                  // a card and never could be reached from here.
                  // The whole red is on offer now, so what is left after the
                  // proposed addition IS what the grid will still show.
                  const stillRed = item.remaining_after
                  return (
                    <tr key={item.category_id}>
                      <td>{item.category_name}</td>
                      <td className="cover-modal__col-num cover-modal__overspent">
                        {formatMoney(-item.overspent)}
                      </td>
                      <td className="cover-modal__col-num cover-modal__covering">
                        +{formatMoney(item.proposed_addition)}
                        {item.credit_overspent > 0 && (
                          <span className="cover-modal__on-card-part">
                            {formatMoney(Math.min(item.credit_overspent, item.proposed_addition))}{' '}
                            retires card debt
                          </span>
                        )}
                      </td>
                      <td className="cover-modal__col-num">
                        {stillRed > 0 ? formatMoney(-stillRed) : formatMoney(0)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {preview.total_addition <= 0 && (
              <p className="cover-modal__no-funds">
                Ready to Assign is empty — add or move money there first.
              </p>
            )}
          </>
        )}
        {error && <div className="cover-modal__error">{error}</div>}
      </div>
    </Dialog>
  )
}
