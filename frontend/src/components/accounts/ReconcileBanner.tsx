import { useState, useRef, useEffect } from 'react'
import { CheckCircle } from 'lucide-react'
import {
  useReconciliationStatus,
  useCreateAdjustment,
  useFinishReconciliation,
} from '../../api/reconciliation'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import './ReconcileBanner.css'

interface Props {
  accountId: string
  accountName: string
}

export function ReconcileBanner({ accountId, accountName }: Props) {
  const { formatMoney } = useFormatters()
  const {
    reconcileStatementBalance,
    reconcileAdjustmentTxnId,
    setReconcileStatementBalance,
    setReconcileAdjustmentTxnId,
    cancelReconciliation,
  } = useUIStore()

  // "question" shows "Does your balance match $X?", "input" shows the custom balance field,
  // "reconciling" shows the diff + finish step
  const [showInput, setShowInput] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const step = reconcileStatementBalance === null ? (showInput ? 'input' : 'question') : 'reconciling'

  const { data: status } = useReconciliationStatus(accountId, {
    refetchInterval: step === 'reconciling' ? 1000 : undefined,
  })

  const createAdjustment = useCreateAdjustment(accountId)
  const finish = useFinishReconciliation(accountId)

  const clearedBalance = Number(status?.cleared_balance ?? 0)
  const statementBalance = reconcileStatementBalance ?? 0
  const difference = statementBalance - clearedBalance
  const isBalanced = Math.abs(difference) < 0.005

  // Focus the input when it becomes visible
  useEffect(() => {
    if (showInput) inputRef.current?.focus()
  }, [showInput])

  function handleYes() {
    // The bank balance matches the cleared balance
    setReconcileStatementBalance(clearedBalance)
  }

  function handleNo() {
    // Show the input field for the actual bank balance
    setShowInput(true)
  }

  function handleContinue() {
    const balance = parseFloat(inputValue.replace(/[^0-9.-]/g, ''))
    if (!isNaN(balance)) {
      setReconcileStatementBalance(balance)
    }
  }

  async function handleCreateAdjustment() {
    const txn = await createAdjustment.mutateAsync(difference)
    setReconcileAdjustmentTxnId(txn.id)
  }

  async function handleFinish() {
    await finish.mutateAsync({
      statement_balance: statementBalance,
      adjustment_transaction_id: reconcileAdjustmentTxnId,
    })
    cancelReconciliation()
  }

  function directionText(): string {
    if (isBalanced) return ''
    const abs = formatMoney(Math.abs(difference))
    return difference > 0
      ? `IGAB is ${abs} lower than your bank`
      : `IGAB is ${abs} higher than your bank`
  }

  return (
    <div className="reconcile-banner">
      <div className="reconcile-banner__inner">
        <div className="reconcile-banner__title">
          <span className="reconcile-banner__label">Reconciling:</span>
          <span className="reconcile-banner__account">{accountName}</span>
        </div>

        {step === 'question' && (
          <div className="reconcile-banner__step-question">
            <span className="reconcile-banner__question">
              Does your bank balance match{' '}
              <strong>{formatMoney(clearedBalance)}</strong>?
            </span>
          </div>
        )}

        {step === 'input' && (
          <div className="reconcile-banner__step-input">
            <span className="reconcile-banner__hint">
              Enter your current bank balance:
            </span>
            <input
              ref={inputRef}
              type="text"
              inputMode="decimal"
              className="reconcile-banner__input"
              placeholder="0.00"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleContinue()}
            />
          </div>
        )}

        {step === 'reconciling' && (
          <div className="reconcile-banner__step-reconciling">
            <div className="reconcile-banner__balances">
              <div className="reconcile-banner__balance-item">
                <span className="reconcile-banner__balance-label">Statement</span>
                <span className="reconcile-banner__balance-value">
                  {formatMoney(statementBalance)}
                </span>
              </div>
              <div className="reconcile-banner__balance-item">
                <span className="reconcile-banner__balance-label">Cleared</span>
                <span className="reconcile-banner__balance-value">
                  {formatMoney(clearedBalance)}
                </span>
              </div>
              <div className="reconcile-banner__balance-item">
                <span className="reconcile-banner__balance-label">Difference</span>
                <span
                  className={`reconcile-banner__balance-value reconcile-banner__difference ${
                    isBalanced
                      ? 'reconcile-banner__difference--ok'
                      : 'reconcile-banner__difference--off'
                  }`}
                >
                  {isBalanced ? (
                    <>
                      <CheckCircle size={13} />
                      {' '}Balanced
                    </>
                  ) : (
                    formatMoney(difference)
                  )}
                </span>
              </div>
            </div>
            {!isBalanced && (
              <p className="reconcile-banner__direction">{directionText()}</p>
            )}
            {isBalanced && (
              <p className="reconcile-banner__direction reconcile-banner__direction--ok">
                Ready to finish reconciling!
              </p>
            )}
          </div>
        )}

        <div className="reconcile-banner__actions">
          {step === 'question' && (
            <>
              <button className="reconcile-banner__btn" onClick={cancelReconciliation}>
                Cancel
              </button>
              <button className="reconcile-banner__btn" onClick={handleNo}>
                No
              </button>
              <button
                className="reconcile-banner__btn reconcile-banner__btn--primary"
                onClick={handleYes}
              >
                Yes
              </button>
            </>
          )}
          {step === 'input' && (
            <>
              <button className="reconcile-banner__btn" onClick={cancelReconciliation}>
                Cancel
              </button>
              <button
                className="reconcile-banner__btn reconcile-banner__btn--primary"
                onClick={handleContinue}
                disabled={!inputValue.trim()}
              >
                Continue
              </button>
            </>
          )}
          {step === 'reconciling' && (
            <>
              {!isBalanced && (
                <button
                  className="reconcile-banner__btn reconcile-banner__btn--adjust"
                  onClick={handleCreateAdjustment}
                  disabled={createAdjustment.isPending}
                >
                  {createAdjustment.isPending ? 'Creating…' : 'Create Adjustment'}
                </button>
              )}
              <button className="reconcile-banner__btn" onClick={cancelReconciliation}>
                Cancel
              </button>
              <button
                className="reconcile-banner__btn reconcile-banner__btn--primary"
                onClick={handleFinish}
                disabled={!isBalanced || finish.isPending}
              >
                {finish.isPending ? 'Finishing…' : 'Finish Reconciling'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
