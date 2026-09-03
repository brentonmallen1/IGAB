import { useState } from 'react'
import { useUpsertTarget, useDeleteTarget } from '../../api/targets'
import type { CategoryTarget } from '../../types'
import { TARGET_TYPES, buildTargetPayload } from './targetForm'
import { Dialog } from '../common/Dialog/Dialog'
import './TargetEditor.css'

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
  const [error, setError] = useState<string | null>(null)

  const upsert = useUpsertTarget(categoryId)
  const del = useDeleteTarget(categoryId)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const result = buildTargetPayload(targetType, amount, targetDate)
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
    >
      <form onSubmit={handleSubmit} className="target-editor__form">
        <label className="target-editor__label">
          Type
          <select
            className="target-editor__select"
            value={targetType}
            onChange={(e) => setTargetType(e.target.value)}
          >
            {TARGET_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>

        <label className="target-editor__label">
          Amount
          <input
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            className="target-editor__input"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </label>

        {(targetType === 'needed_for_spending' || targetType === 'savings_balance') && (
          <label className="target-editor__label">
            Target Date
            <input
              type="date"
              className="target-editor__input"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
            />
          </label>
        )}

        {error && (
          <div className="target-editor__error" role="alert">
            {error}
          </div>
        )}
        <div className="target-editor__actions">
          <button type="submit" className="target-editor__btn target-editor__btn--primary">
            Save
          </button>
          {existing && (
            <button
              type="button"
              className="target-editor__btn target-editor__btn--danger"
              onClick={handleDelete}
            >
              Remove
            </button>
          )}
          <button type="button" className="target-editor__btn" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  )
}
