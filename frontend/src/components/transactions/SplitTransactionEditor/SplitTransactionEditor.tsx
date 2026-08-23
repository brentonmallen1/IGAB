import { Plus, Trash2, X } from 'lucide-react'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import { useCreateTransaction, useDeleteTransaction } from '../../../api/transactions'
import { useAppStore } from '../../../stores/appStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { fromCents, toCents } from '../../../utils/money'
import { checkSplit } from '../../../utils/splits'
import { expressionToCents } from '../../../utils/amountExpression'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { Combobox, type ComboboxOption } from '../../common/Combobox/Combobox'
import type { Category, CategoryGroup, Transaction } from '../../../types'
import './SplitTransactionEditor.css'

interface Props {
  transaction: Transaction
  categories: Category[]
  categoryGroups: CategoryGroup[]
}

export function SplitTransactionEditor({ transaction: txn, categories, categoryGroups }: Props) {
  const { formatMoney } = useFormatters()
  const budgetId = useAppStore((s) => s.currentBudgetId!)
  const { splitEditing, updateSplit, addSplit, removeSplit, stopSplitEditing } = useTransactionEditStore()
  const createTxn = useCreateTransaction(budgetId)
  const deleteTxn = useDeleteTransaction(budgetId)

  if (!splitEditing || splitEditing.transactionId !== txn.id) return null

  const { totalAmount, splits } = splitEditing
  const check = checkSplit(Math.abs(toCents(totalAmount)), splits)
  const { remainingCents, isValid } = check
  const remaining = fromCents(remainingCents)

  const categoryOptions: ComboboxOption[] = categories.map((c) => {
    const group = categoryGroups.find((g) => g.id === c.category_group_id)
    return { id: c.id, label: c.name, group: group?.name ?? '' }
  })

  async function handleSave() {
    if (!isValid) return
    const sign = totalAmount < 0 ? -1 : 1
    // Create the split version first, then remove the original row — the
    // split replaces it (previously both survived and double-counted).
    await createTxn.mutateAsync({
      account_id: txn.account_id,
      date: txn.date,
      amount: totalAmount,
      payee_id: txn.payee_id ?? undefined,
      memo: txn.memo ?? undefined,
      cleared: txn.cleared === 'reconciled' || txn.cleared === 'pending' ? 'cleared' : txn.cleared,
      splits: splits.map((s) => ({
        amount: (expressionToCents(s.amount) / 100) * sign,
        category_id: s.categoryId ?? undefined,
        memo: s.memo || undefined,
      })),
    })
    await deleteTxn.mutateAsync({ id: txn.id, accountId: txn.account_id })
    stopSplitEditing()
  }

  return (
    <div className="split-editor">
      <div className="split-editor__header">
        <span className="split-editor__title">
          Split <strong>{formatMoney(Math.abs(totalAmount))}</strong>
        </span>
        <button className="split-editor__close" onClick={stopSplitEditing} aria-label="Cancel split" title="Cancel">
          <X size={14} />
        </button>
      </div>

      <div className="split-editor__rows">
        {splits.map((split, i) => (
          <div key={split.tempId} className="split-editor__row">
            <span className="split-editor__row-num">{i + 1}</span>

            <div className="split-editor__category">
              <Combobox
                value={split.categoryId}
                options={categoryOptions}
                onChange={(id) => updateSplit(split.tempId, { categoryId: id })}
                placeholder="Category…"
              />
            </div>

            <AmountInput
              className="split-editor__amount"
              value={split.amount}
              onValueChange={(v) => updateSplit(split.tempId, { amount: v })}
              placeholder="0.00"
            />

            <input
              className="split-editor__memo"
              type="text"
              value={split.memo}
              onChange={(e) => updateSplit(split.tempId, { memo: e.target.value })}
              placeholder="Memo…"
            />

            <button
              className="split-editor__remove"
              onClick={() => removeSplit(split.tempId)}
              disabled={splits.length <= 2}
              title="Remove split"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
      </div>

      <div className="split-editor__footer">
        <button className="split-editor__add-btn" onClick={addSplit}>
          <Plus size={12} />
          Add split
        </button>

        <div className={`split-editor__remaining ${remainingCents === 0 ? 'split-editor__remaining--done' : ''}`}>
          {remainingCents === 0
            ? 'Fully assigned'
            : `Remaining: ${formatMoney(remaining)}`}
        </div>

        <div className="split-editor__actions">
          <button className="split-editor__cancel" onClick={stopSplitEditing}>Cancel</button>
          <button
            className="split-editor__save"
            onClick={handleSave}
            disabled={!isValid || createTxn.isPending || deleteTxn.isPending}
          >
            Save Split
          </button>
        </div>
      </div>
    </div>
  )
}
