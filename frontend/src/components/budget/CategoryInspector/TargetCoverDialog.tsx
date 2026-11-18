import { useState } from 'react'
import { apiErrorMessage } from '../../../api/client'
import { useFormatters } from '../../../hooks/useFormatters'
import { sharedPick, withPick, type TargetCoverRow } from '../../../utils/targetCover'
import { Dialog } from '../../common/Dialog/Dialog'
import { TargetCoverChoice } from '../TargetCoverChoice/TargetCoverChoice'
import './TargetCoverDialog.css'

interface Props {
  /** The overspent envelopes — only those offered Cover + target. */
  rows: TargetCoverRow[]
  /** Targeted envelopes in the selection without the choice: they take their
   *  target amount whatever is picked here. */
  othersCount: number
  /** Which rows start as Cover + target. */
  initialCoverIds: readonly string[]
  /** Runs the press with the chosen `cover_ids`; a rejection is shown in the
   *  footer and the dialog stays open. */
  onConfirm: (coverIds: string[]) => Promise<unknown>
  onClose: () => void
}

/**
 * Target Amount over several envelopes, when some of them have spent past
 * what they were given: for each, assign the target (spending already
 * covered counts toward it) or cover the spending and assign the target on
 * top. Only those envelopes are listed; the rest go ahead with their target.
 */
export function TargetCoverDialog({
  rows,
  othersCount,
  initialCoverIds,
  onConfirm,
  onClose,
}: Props) {
  const { formatMoney } = useFormatters()
  const [coverIds, setCoverIds] = useState<Set<string>>(() => new Set(initialCoverIds))
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const offered = rows.map((r) => r.categoryId)
  const all = sharedPick(offered, coverIds)
  const total = rows.reduce((sum, r) => sum + (coverIds.has(r.categoryId) ? r.cover : r.target), 0)

  async function confirm() {
    setError(null)
    setPending(true)
    try {
      await onConfirm(offered.filter((id) => coverIds.has(id)))
      onClose()
    } catch (err: unknown) {
      setError(apiErrorMessage(err, 'Could not assign the targets'))
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      title="Cover overspending too?"
      onClose={onClose}
      historyKey="target-cover"
      footer={
        <div className="dialog-actions">
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={onClose}
              disabled={pending}
            >
              Cancel
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn--primary"
              onClick={() => void confirm()}
              disabled={pending}
            >
              {pending ? 'Assigning…' : 'Assign targets'}
            </button>
          </div>
        </div>
      }
    >
      <div className="dialog__body dialog-form target-cover-dialog">
        <p className="dialog-form__hint">
          {rows.length === 1 ? 'This category has' : 'These categories have'} spent everything they
          were given. Target counts money that covered spending toward the target; Cover + target
          covers the spending and assigns the target on top.
        </p>
        {rows.length > 1 && (
          <div className="target-cover-dialog__row target-cover-dialog__row--all">
            <span className="target-cover-dialog__name">Same for all</span>
            <TargetCoverChoice
              value={all}
              label="Same for all"
              onChange={(pick) => setCoverIds(new Set(pick === 'cover' ? offered : []))}
              disabled={pending}
            />
          </div>
        )}
        <ul className="target-cover-dialog__list">
          {rows.map((r) => (
            <li key={r.categoryId} className="target-cover-dialog__row">
              <span className="target-cover-dialog__name">{r.name}</span>
              <TargetCoverChoice
                value={coverIds.has(r.categoryId) ? 'cover' : 'target'}
                label={r.name}
                targetAmount={r.target}
                coverAmount={r.cover}
                onChange={(pick) => setCoverIds((ids) => withPick(ids, r.categoryId, pick))}
                disabled={pending}
              />
            </li>
          ))}
        </ul>
        <p className="dialog-form__hint">
          These assign {formatMoney(total)} in total.
          {othersCount > 0 &&
            ` ${othersCount === 1 ? '1 other category takes its' : `${othersCount} other categories take their`} target amount.`}
        </p>
      </div>
    </Dialog>
  )
}
