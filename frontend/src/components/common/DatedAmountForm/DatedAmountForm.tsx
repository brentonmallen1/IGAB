import { useState } from 'react'
import { parseAmountInput } from '../../../utils/money'
import './DatedAmountForm.css'

interface Props {
  title: string
  amountLabel: string
  placeholder?: string
  pending: boolean
  /** `date` is null when the field was left blank — the caller decides the
   *  default (the server stamps today, like the Guide's `as_of`). */
  onSubmit: (amount: number, date: string | null) => Promise<void> | void
  onClose: () => void
}

/**
 * One dated figure, stated: "it is worth/I owe X, as of D".
 *
 * Extracted from LiabilityPage's balance overlay the day AssetPage needed the
 * identical form — the moment a copy is still free to fix. The shape is the
 * point: a self-reported number without its date is how the freshest point on
 * the net-worth chart becomes the one with no provenance, so the date input
 * travels with the amount everywhere this form is used.
 */
export function DatedAmountForm({
  title,
  amountLabel,
  placeholder,
  pending,
  onSubmit,
  onClose,
}: Props) {
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const parsed = parseAmountInput(amount)
    if (isNaN(parsed) || parsed < 0) return
    await onSubmit(parsed, date || null)
  }

  return (
    <div
      className="daf__overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <form className="daf__form" onSubmit={handleSubmit}>
        <h3>{title}</h3>
        <label>
          <span>{amountLabel}</span>
          <input
            type="number"
            min="0"
            step="0.01"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            autoFocus
            placeholder={placeholder}
          />
        </label>
        <label>
          <span>As of (optional — defaults to today)</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <div className="daf__actions">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={pending}>
            {pending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  )
}
