import { useState } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { useTarget, useUpsertTarget, useDeleteTarget } from '../../../api/targets'
import { useFormatters } from '../../../hooks/useFormatters'
import { TARGET_TYPES, WEEKDAYS, buildTargetPayload, targetTypeLabel } from '../targetForm'
import { MAX_FUNDING_DAY } from '../../../utils/targets'

interface Props {
  categoryId: string
}

export function TargetSection({ categoryId }: Props) {
  const { formatMoney, formatDate } = useFormatters()
  const [isEditing, setIsEditing] = useState(false)
  const [targetType, setTargetType] = useState('monthly_funding')
  const [amount, setAmount] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [weekday, setWeekday] = useState('')
  const [checkAfterDay, setCheckAfterDay] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: target } = useTarget(categoryId)
  const upsert = useUpsertTarget(categoryId)
  const del = useDeleteTarget(categoryId)

  function startEdit() {
    setTargetType(target?.target_type ?? 'monthly_funding')
    setAmount(target ? String(target.target_amount) : '')
    setTargetDate(target?.target_date ?? '')
    setWeekday(target?.weekday != null ? String(target.weekday) : '')
    setCheckAfterDay(target?.check_after_day != null ? String(target.check_after_day) : '')
    setIsEditing(true)
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    const result = buildTargetPayload({ targetType, amount, targetDate, weekday, checkAfterDay })
    if (!result.ok) {
      setError(result.error)
      return
    }
    setError(null)
    await upsert.mutateAsync(result.payload)
    setIsEditing(false)
  }

  async function handleDelete() {
    await del.mutateAsync()
    setIsEditing(false)
  }

  if (isEditing) {
    return (
      <div className="inspector-section">
        <div className="inspector-section__title">Target</div>
        <form onSubmit={handleSave} className="inspector-target-form">
          <label className="inspector-field">
            <span>Type</span>
            <select
              className="inspector-select"
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
          <label className="inspector-field">
            <span>Amount</span>
            <input
              type="number"
              step="0.01"
              min="0"
              className="inspector-input"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              required
            />
          </label>
          {targetType === 'weekly_funding' && (
            <label className="inspector-field">
              <span>Every</span>
              <select
                className="inspector-select"
                value={weekday}
                onChange={(e) => setWeekday(e.target.value)}
                required
              >
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
            <label className="inspector-field">
              <span>By (optional)</span>
              <input
                type="date"
                className="inspector-input"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
              />
            </label>
          )}
          <label className="inspector-field">
            <span>Check after day</span>
            <input
              type="number"
              inputMode="numeric"
              min="1"
              max={MAX_FUNDING_DAY}
              step="1"
              className="inspector-input"
              value={checkAfterDay}
              onChange={(e) => setCheckAfterDay(e.target.value)}
              placeholder="Budget's funding day"
            />
          </label>
          {error && (
            <div className="inspector-error" role="alert">
              {error}
            </div>
          )}
          <div className="inspector-target-form__actions">
            <button
              type="submit"
              className="inspector-btn inspector-btn--primary"
              disabled={upsert.isPending}
            >
              Save
            </button>
            {target && (
              <button
                type="button"
                className="inspector-btn inspector-btn--danger"
                onClick={handleDelete}
                disabled={del.isPending}
              >
                Remove
              </button>
            )}
            <button type="button" className="inspector-btn" onClick={() => setIsEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    )
  }

  return (
    <div className="inspector-section">
      <div className="inspector-section__header">
        <span className="inspector-section__title">Target</span>
        {target && (
          <div className="inspector-section__actions">
            <button
              className="inspector-icon-btn"
              onClick={startEdit}
              aria-label="Edit target"
              title="Edit target"
            >
              <Pencil size={12} />
            </button>
            <button
              className="inspector-icon-btn inspector-icon-btn--danger"
              onClick={handleDelete}
              aria-label="Remove target"
              title="Remove target"
            >
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>
      {target ? (
        <div className="inspector-target-display">
          <div className="inspector-target-display__type">
            {targetTypeLabel(target.target_type)}
            {target.target_type === 'weekly_funding' && target.weekday != null
              ? ` · every ${WEEKDAYS[target.weekday]?.label ?? ''}`
              : ''}
          </div>
          <div className="inspector-target-display__amount">
            {formatMoney(target.target_amount)}
          </div>
          {target.target_date && (
            <div className="inspector-target-display__date">
              By {formatDate(target.target_date)}
            </div>
          )}
          {target.check_after_day != null && (
            <div className="inspector-target-display__date">
              Checked after day {target.check_after_day}
            </div>
          )}
        </div>
      ) : (
        <button className="inspector-create-btn" onClick={startEdit}>
          + Create Target
        </button>
      )}
    </div>
  )
}
