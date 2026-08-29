import { CheckCircle, X } from 'lucide-react'
import {
  useReconciliationStatus,
  useCreateAdjustment,
  useFinishReconciliation,
} from '../../api/reconciliation'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import { fromCents, toCents } from '../../utils/money'
import './ReconcileStatusBar.css'

interface Props {
  accountId: string
}

/**
 * Live difference tracker for an in-progress reconciliation. It stays on
 * screen while the user clears, adds and edits rows, and the difference
 * follows along — polling once a second, plus the ['reconcile-status']
 * invalidations every transaction mutation already fires.
 *
 * Stacks above the selection bar when both are up, so bulk-clearing rows
 * mid-reconcile never hides the number the user is working toward.
 */
export function ReconcileStatusBar({ accountId }: Props) {
  const { formatMoney } = useFormatters()
  const {
    reconcileStatementBalance,
    reconcileAdjustmentTxnId,
    setReconcileAdjustmentTxnId,
    cancelReconciliation,
    selectedTransactionIds,
  } = useUIStore()

  const { data: status } = useReconciliationStatus(accountId, { refetchInterval: 1000 })
  const createAdjustment = useCreateAdjustment(accountId)
  const finish = useFinishReconciliation(accountId)

  const clearedBalance = Number(status?.cleared_balance ?? 0)
  const statementBalance = reconcileStatementBalance ?? 0
  // In cents, not floats. `100.10 - 7865.90` is -7765.799999999999 in IEEE
  // 754, and the API's Money type rejects anything past four decimal places —
  // so the float difference 422'd on most real statement pairs. Every other
  // amount the client posts already goes through cents (MoveMoneyForm,
  // AssignManualTab); this was the straggler.
  const differenceCents = toCents(statementBalance) - toCents(clearedBalance)
  const difference = fromCents(differenceCents)
  const isBalanced = differenceCents === 0

  async function handleCreateAdjustment() {
    const txn = await createAdjustment.mutateAsync(difference)
    setReconcileAdjustmentTxnId(txn.id)
  }

  async function handleFinish() {
    await finish.mutateAsync({
      statement_balance: fromCents(toCents(statementBalance)),
      adjustment_transaction_id: reconcileAdjustmentTxnId,
    })
    cancelReconciliation()
  }

  const differenceHint = isBalanced
    ? 'Everything matches'
    : difference > 0
      ? `IGAB is ${formatMoney(Math.abs(difference))} lower than your bank`
      : `IGAB is ${formatMoney(Math.abs(difference))} higher than your bank`

  return (
    <div
      className={`reconcile-bar${selectedTransactionIds.size > 0 ? ' reconcile-bar--stacked' : ''}`}
      role="status"
    >
      <button
        className="reconcile-bar__close"
        onClick={cancelReconciliation}
        title="Stop reconciling"
        aria-label="Stop reconciling"
      >
        <X size={14} />
      </button>

      <span className="reconcile-bar__label">Reconciling</span>

      <div className="reconcile-bar__divider" />

      <span className="reconcile-bar__stat">
        <span className="reconcile-bar__stat-label">Statement</span>
        <span className="reconcile-bar__stat-value">{formatMoney(statementBalance)}</span>
      </span>
      <span className="reconcile-bar__stat">
        <span className="reconcile-bar__stat-label">Cleared</span>
        <span className="reconcile-bar__stat-value">{formatMoney(clearedBalance)}</span>
      </span>
      <span
        className={`reconcile-bar__stat reconcile-bar__stat--difference${isBalanced ? ' reconcile-bar__stat--balanced' : ''}`}
        title={differenceHint}
      >
        <span className="reconcile-bar__stat-label">Difference</span>
        <span className="reconcile-bar__difference">
          {isBalanced ? <CheckCircle size={15} /> : null}
          {isBalanced ? 'Balanced' : formatMoney(difference)}
        </span>
      </span>

      <div className="reconcile-bar__divider" />

      {isBalanced ? (
        <button
          className="reconcile-bar__btn reconcile-bar__btn--primary"
          onClick={handleFinish}
          disabled={finish.isPending}
        >
          {finish.isPending ? 'Finishing…' : 'Finish reconciling'}
        </button>
      ) : (
        <button
          className="reconcile-bar__btn"
          onClick={handleCreateAdjustment}
          disabled={createAdjustment.isPending}
          title="Add a cleared transaction covering the difference"
        >
          {createAdjustment.isPending ? 'Creating…' : 'Create adjustment'}
        </button>
      )}
    </div>
  )
}
