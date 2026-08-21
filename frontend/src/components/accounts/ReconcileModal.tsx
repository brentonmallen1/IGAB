import { useState, useRef, useEffect } from 'react'
import { Landmark } from 'lucide-react'
import { Modal } from '../common/Modal/Modal'
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
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: status } = useReconciliationStatus(accountId)
  const clearedBalance = Number(status?.cleared_balance ?? 0)

  useEffect(() => {
    if (showInput) inputRef.current?.focus()
  }, [showInput])

  function handleContinue() {
    const balance = parseFloat(inputValue.replace(/[^0-9.-]/g, ''))
    if (!isNaN(balance)) setReconcileStatementBalance(balance)
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

        {showInput && (
          <div className="reconcile-modal__input-row">
            <label htmlFor="reconcile-balance-input" className="reconcile-modal__input-label">
              What does your bank say?
            </label>
            <input
              id="reconcile-balance-input"
              ref={inputRef}
              type="text"
              inputMode="decimal"
              className="reconcile-modal__input"
              placeholder="0.00"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleContinue()}
            />
          </div>
        )}

        <div className="reconcile-modal__actions">
          <button className="reconcile-modal__btn" onClick={cancelReconciliation}>
            Cancel
          </button>
          {showInput ? (
            <button
              className="reconcile-modal__btn reconcile-modal__btn--primary"
              onClick={handleContinue}
              disabled={!inputValue.trim()}
            >
              Continue
            </button>
          ) : (
            <>
              <button className="reconcile-modal__btn" onClick={() => setShowInput(true)}>
                No
              </button>
              <button
                className="reconcile-modal__btn reconcile-modal__btn--primary"
                onClick={() => setReconcileStatementBalance(clearedBalance)}
              >
                Yes
              </button>
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
