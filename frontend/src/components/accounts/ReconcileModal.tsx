import { parseAmountInput } from '../../utils/money'
import { useState, useRef, useEffect } from 'react'
import { Landmark } from 'lucide-react'
import { Modal } from '../common/Modal/Modal'
// Modal rather than Dialog — this is one question, not a titled panel — so the
// shared field and button styles are imported here rather than through Dialog.
import '../common/Dialog/DialogForm.css'
import { useReconciliationStatus } from '../../api/reconciliation'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import './ReconcileModal.css'

interface Props {
  accountId: string
  accountName: string
}

/**
 * The opening question of a reconciliation: does the bank agree with what
 * IGAB has cleared? Answering it is the whole job of this modal — once a
 * statement balance is set, ReconcileStatusBar takes over and this closes.
 */
export function ReconcileModal({ accountId, accountName }: Props) {
  const { formatMoney } = useFormatters()
  const { setReconcileStatementBalance, cancelReconciliation } = useUIStore()

  const [showInput, setShowInput] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: status } = useReconciliationStatus(accountId)
  const clearedBalance = Number(status?.cleared_balance ?? 0)

  useEffect(() => {
    if (showInput) inputRef.current?.focus()
  }, [showInput])

  function handleContinue(e: React.FormEvent) {
    e.preventDefault()
    if (!showInput) return
    // Stripping to [0-9.-] first turned "1.234,56" into "1.234.56".
    // parseAmountInput knows both separator conventions; the sign is
    // recovered separately because a statement balance may be negative.
    const negative = inputValue.trim().startsWith('-')
    const magnitude = parseAmountInput(inputValue.replace('-', ''))
    const balance = negative ? -magnitude : magnitude
    if (!inputValue.trim() || isNaN(balance)) {
      // It used to do nothing at all here, and Continue simply did not work.
      setError('Enter the balance your bank shows')
      return
    }
    setError(null)
    setReconcileStatementBalance(balance)
  }

  return (
    <Modal onClose={cancelReconciliation} className="reconcile-modal-overlay">
      <div
        className="reconcile-modal"
        role="dialog"
        aria-modal
        aria-labelledby="reconcile-modal-title"
      >
        <span className="reconcile-modal__eyebrow">
          <Landmark size={13} />
          Reconciling {accountName}
        </span>

        <h2 id="reconcile-modal-title" className="reconcile-modal__question">
          Does your bank balance match
        </h2>
        <p className="reconcile-modal__amount">{formatMoney(clearedBalance)}</p>

        {status && (status.uncleared_count > 0 || status.pending_count > 0) && (
          <p className="reconcile-modal__context">
            {[
              status.uncleared_count > 0 ? `${status.uncleared_count} uncleared` : null,
              status.pending_count > 0 ? `${status.pending_count} pending` : null,
            ]
              .filter(Boolean)
              .join(' · ')}{' '}
            not counted in this balance
          </p>
        )}

        <form className="dialog-form reconcile-modal__form" onSubmit={handleContinue}>
          {showInput && (
            <div className="dialog-form__field reconcile-modal__field">
              <label htmlFor="reconcile-balance-input">What does your bank say?</label>
              <input
                id="reconcile-balance-input"
                ref={inputRef}
                type="text"
                inputMode="decimal"
                className="reconcile-modal__input"
                placeholder="0.00"
                value={inputValue}
                onChange={(e) => {
                  setInputValue(e.target.value)
                  setError(null)
                }}
              />
              {error && <p className="dialog-form__error">{error}</p>}
            </div>
          )}

          <div className="reconcile-modal__actions">
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary reconcile-modal__btn"
              onClick={cancelReconciliation}
            >
              Cancel
            </button>
            {showInput ? (
              <button type="submit" className="dialog-btn dialog-btn--primary reconcile-modal__btn">
                Continue
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="dialog-btn dialog-btn--secondary reconcile-modal__btn"
                  onClick={() => setShowInput(true)}
                >
                  No
                </button>
                <button
                  type="button"
                  className="dialog-btn dialog-btn--primary reconcile-modal__btn"
                  onClick={() => setReconcileStatementBalance(clearedBalance)}
                >
                  Yes
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </Modal>
  )
}
