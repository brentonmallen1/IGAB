import { useState } from 'react'
import { parseAmountInput } from '../../../utils/money'
import { Dialog } from '../Dialog/Dialog'

/** The form lives in the scroll region; its submit button lives in the pinned
 *  footer, and `form=` is what joins them. */
const FORM_ID = 'daf-form'

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
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Never a silent return: an unreadable figure used to leave Save doing
    // nothing at all, with no word as to why.
    const parsed = parseAmountInput(amount)
    if (isNaN(parsed) || parsed < 0) return setError('Enter an amount of zero or more')
    setError(null)
    await onSubmit(parsed, date || null)
  }

  return (
    <Dialog
      title={title}
      onClose={onClose}
      historyKey="dated-amount"
      footer={
        <div className="dialog-actions">
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              form={FORM_ID}
              className="dialog-btn dialog-btn--primary"
              disabled={pending}
            >
              {pending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      }
    >
      <form id={FORM_ID} className="dialog-form" onSubmit={handleSubmit} noValidate>
        <label className="dialog-form__field">
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
        <label className="dialog-form__field">
          <span>As of (optional — defaults to today)</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      </form>
    </Dialog>
  )
}
