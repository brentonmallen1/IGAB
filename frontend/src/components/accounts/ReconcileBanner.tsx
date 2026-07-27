import { useState } from 'react'
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

  const [inputValue, setInputValue] = useState('')
  const step = reconcileStatementBalance === null ? 'input' : 'reconciling'

  const { data: status } = useReconciliationStatus(accountId, {
    refetchInterval: step === 'reconciling' ? 1000 : undefined,
  })

  const createAdjustment = useCreateAdjustment(accountId)
  const finish = useFinishReconciliation(accountId)

  const clearedBalance = Number(status?.cleared_balance ?? 0)
  const statementBalance = reconcileStatementBalance ?? 0
  const difference = statementBalance - clearedBalance
  const isBalanced = Math.abs(difference) < 0.005

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

        {step === 'input' && (
          <div className="reconcile-banner__step-input">
            <span className="reconcile-banner__hint">
              Your cleared balance is{' '}
              <strong>{formatMoney(Number(status?.cleared_balance ?? 0))}</strong>.
              Enter your current bank balance:
            </span>
            <div className="reconcile-banner__input-row">
              <label className="reconcile-banner__input-label">Statement balance</label>
              <input
                type="number"
                step="0.01"
                className="reconcile-banner__input"
                placeholder="0.00"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleContinue()}
                autoFocus
              />
            </div>
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
