import { useId, useState } from 'react'
import { useUpsertTarget, useDeleteTarget } from '../../api/targets'
import type { CategoryTarget } from '../../types'
import { TARGET_TYPES, WEEKDAYS, buildTargetPayload } from './targetForm'
import { Dialog } from '../common/Dialog/Dialog'
import './TargetEditor.css'
import { MAX_FUNDING_DAY } from '../../utils/targets'

/** The form scrolls; its submit button is in the pinned footer, joined by id. */
const FORM_ID = 'target-editor-form'

interface Props {
  categoryId: string
  categoryName: string
  existing: CategoryTarget | null
  onClose: () => void
}

export function TargetEditor({ categoryId, categoryName, existing, onClose }: Props) {
  const [targetType, setTargetType] = useState(existing?.target_type ?? 'monthly_funding')
  const [amount, setAmount] = useState(existing ? String(existing.target_amount) : '')
  const [targetDate, setTargetDate] = useState(existing?.target_date ?? '')
  const [weekday, setWeekday] = useState(existing?.weekday != null ? String(existing.weekday) : '')
  const [checkAfterDay, setCheckAfterDay] = useState(
    existing?.check_after_day != null ? String(existing.check_after_day) : ''
  )
  const [error, setError] = useState<string | null>(null)
  const typeId = useId()
  const checkAfterId = useId()

  const upsert = useUpsertTarget(categoryId)
  const del = useDeleteTarget(categoryId)
  const help = TARGET_TYPES.find((t) => t.value === targetType)?.help
  const isPending = upsert.isPending || del.isPending

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const result = buildTargetPayload({ targetType, amount, targetDate, weekday, checkAfterDay })
    if (!result.ok) {
      setError(result.error)
      return
    }
    setError(null)
    await upsert.mutateAsync(result.payload)
    onClose()
  }

  async function handleDelete() {
    await del.mutateAsync()
    onClose()
  }

  return (
    <Dialog
      title={`Target: ${categoryName}`}
      onClose={onClose}
      historyKey="target-editor"
      className="target-editor"
      footer={
        <div className="dialog-actions">
          {existing && (
            <button
              type="button"
              className="dialog-btn dialog-btn--danger"
              onClick={handleDelete}
              disabled={isPending}
            >
              Remove
            </button>
          )}
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
              disabled={isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              form={FORM_ID}
              className="dialog-btn dialog-btn--primary"
              disabled={isPending}
            >
              {upsert.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      }
    >
      {/* noValidate: buildTargetPayload is the validation, and its message
          belongs in the footer — a browser bubble on `required` pre-empted it. */}
      <form id={FORM_ID} onSubmit={handleSubmit} className="dialog-form" noValidate>
        <div className="dialog-form__field">
          {/* The hint sits outside the label so it is not part of the name. */}
          <label htmlFor={typeId}>Type</label>
          <select id={typeId} value={targetType} onChange={(e) => setTargetType(e.target.value)}>
            {TARGET_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          {help && <p className="dialog-form__hint">{help}</p>}
        </div>

        <label className="dialog-form__field">
          <span>Amount</span>
          <input
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>

        {targetType === 'weekly_funding' && (
          <label className="dialog-form__field">
            <span>Every</span>
            <select value={weekday} onChange={(e) => setWeekday(e.target.value)}>
              <option value="">Pick a day…</option>
              {WEEKDAYS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
        )}

        {targetType === 'savings_balance' && (
          <label className="dialog-form__field">
            <span>By (optional)</span>
            <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </label>
        )}

        <div className="dialog-form__field">
          <label htmlFor={checkAfterId}>Check after day (optional)</label>
          <input
            id={checkAfterId}
            type="number"
            inputMode="numeric"
            min="1"
            max={MAX_FUNDING_DAY}
            step="1"
            value={checkAfterDay}
            onChange={(e) => setCheckAfterDay(e.target.value)}
            placeholder="Budget's funding day"
          />
          <p className="dialog-form__hint">
            Until this day of the month an unmet target reads pending, not underfunded.
          </p>
        </div>
      </form>
    </Dialog>
  )
}
