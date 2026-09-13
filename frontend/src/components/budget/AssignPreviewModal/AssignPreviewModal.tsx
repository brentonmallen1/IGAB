import { useState } from 'react'
import { apiErrorMessage } from '../../../api/client'
import { useUndoToast } from '../../../utils/toastUndo'
import { useAssignApply, useAssignPreview } from '../../../api/assign'
import { useFormatters } from '../../../hooks/useFormatters'
import type { AssignStrategy } from '../../../types'
import { STRATEGY_META } from '../AssignDropdown/strategyMeta'
import { Dialog } from '../../common/Dialog/Dialog'
import '../previewDialog.css'
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
  const notify = useUndoToast()
  const [error, setError] = useState<string | null>(null)
  const meta = STRATEGY_META[strategy]
  const tbaAfter = Number(preview?.tba_after ?? 0)
  const toAssign = Number(preview?.to_assign ?? 0)
  const toReturn = Number(preview?.to_return ?? 0)
  const hasChanges = preview?.items.some((i) => i.delta !== 0) ?? false

  async function handleApply() {
    if (!preview) return
    // Enabled and asked, like every dialog's primary, rather than inert with
    // no reason given.
    if (!hasChanges) {
      setError('Every category already matches this strategy — nothing to apply.')
      return
    }
    setError(null)
    let result: Awaited<ReturnType<typeof apply.mutateAsync>>
    try {
      result = await apply.mutateAsync({ month, strategy })
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Could not apply this strategy'))
      return
    }
    const assigned = result.to_assign
    const returned = result.to_return
    const parts = []
    if (assigned > 0) parts.push(`${formatMoney(assigned)} assigned`)
    if (returned > 0) parts.push(`${formatMoney(returned)} returned to TBA`)
    notify(
      parts.length > 0
        ? `${meta.label}: ${parts.join(', ')} across ${result.categories_changed} categories`
        : `${meta.label}: nothing to change`,
      result.categories_changed > 0 && result.batch_id ? { batch: result.batch_id } : null
    )
    onClose()
  }

  // Dialog pins the footer below the scroll region; which of the two it is
  // depends on whether the preview found anything to change.
  const footer =
    preview && preview.items.length > 0 ? (
      <div className="dialog-actions preview-dialog__actions">
        {error ? (
          <span className="dialog-form__error" role="alert">
            {error}
          </span>
        ) : (
          <div className="preview-dialog__tba">
            <span className="preview-dialog__tba-label">TBA:</span>
            <span className="preview-dialog__tba-value">{formatMoney(preview.tba_before)}</span>
            <span className="preview-dialog__tba-label">→</span>
            <span
              className={`preview-dialog__tba-value ${tbaAfter >= 0 ? 'positive' : 'negative'}`}
            >
              {formatMoney(tbaAfter)}
            </span>
          </div>
        )}
        <div className="dialog-actions__end">
          <button
            type="button"
            className="dialog-btn dialog-btn--secondary"
            onClick={onClose}
            disabled={apply.isPending}
          >
            Cancel
          </button>
          <button
            type="button"
            className="dialog-btn dialog-btn--primary"
            onClick={handleApply}
            disabled={apply.isPending}
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
    ) : !isLoading ? (
      <div className="dialog-actions">
        <div className="dialog-actions__end">
          <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    ) : undefined

  return (
    <Dialog
      title={meta.label}
      onClose={onClose}
      historyKey="assign-preview"
      className="assign-preview-modal"
      footer={footer}
    >
      <div className="preview-dialog__body">
        {isLoading ? (
          <div className="preview-dialog__status">Calculating…</div>
        ) : !preview || preview.items.length === 0 ? (
          <div className="preview-dialog__status">Nothing to change — you're all set.</div>
        ) : (
          <>
            <p className="preview-dialog__description">{meta.description}</p>
            <table className="preview-dialog__table">
              <caption className="sr-only">Per-category changes for {meta.label}</caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col" className="preview-dialog__col-num">
                    Current
                  </th>
                  <th scope="col" className="preview-dialog__col-num">
                    Change
                  </th>
                  <th scope="col" className="preview-dialog__col-num">
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
                      <td className="preview-dialog__col-num">
                        {formatMoney(item.current_assigned)}
                      </td>
                      <td
                        className={`preview-dialog__col-num ${
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
                      <td className="preview-dialog__col-num">{formatMoney(item.new_assigned)}</td>
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
            {/* The consequence a before/after table of ASSIGNED cannot show:
                setting an envelope back to a past figure unfunds money that
                has already been spent from it. Legitimate — it is what the
                strategy means — but it should not be a surprise found in the
                grid afterwards. Stated, not blocked. */}
            {preview.newly_overspent_count > 0 && (
              <div className="assign-preview-modal__overspend-warning">
                Leaves{' '}
                {preview.newly_overspent_count === 1
                  ? '1 category'
                  : `${preview.newly_overspent_count} categories`}{' '}
                overspent by {formatMoney(preview.newly_overspent_total)} in total — money already
                spent from them would stop being funded. Cover Overspending can put it back.
              </div>
            )}
          </>
        )}
      </div>
    </Dialog>
  )
}
