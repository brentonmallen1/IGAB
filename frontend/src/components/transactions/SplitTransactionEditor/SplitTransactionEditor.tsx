import { useEffect } from 'react'
import { Plus, Trash2, X, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import {
  useConvertToSplit,
  useReplaceSplits,
  useTransactionSplits,
} from '../../../api/transactions'
import { useAppStore } from '../../../stores/appStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { fromCents, toCents } from '../../../utils/money'
import { checkSplit, draftsFromLines } from '../../../utils/splits'
import { expressionToCents } from '../../../utils/amountExpression'
import { apiErrorMessage } from '../../../api/client'
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
  const { splitEditing, updateSplit, addSplit, removeSplit, stopSplitEditing, seedSplits } =
    useTransactionEditStore()
  const convertToSplit = useConvertToSplit(budgetId)
  const replaceSplits = useReplaceSplits(budgetId)

  // An existing split's lines live on the server, never in the loaded page.
  const { data: lines } = useTransactionSplits(txn.id, txn.is_split)
  useEffect(() => {
    if (lines) seedSplits(txn.id, draftsFromLines(lines))
  }, [lines, txn.id, seedSplits])

  if (!splitEditing || splitEditing.transactionId !== txn.id) return null

  const { totalAmount, splits, loaded } = splitEditing
  const check = checkSplit(Math.abs(toCents(totalAmount)), splits)
  const { remainingCents, isValid } = check
  const remaining = fromCents(remainingCents)

  const categoryOptions: ComboboxOption[] = categories.map((c) => {
    const group = categoryGroups.find((g) => g.id === c.category_group_id)
    return { id: c.id, label: c.name, group: group?.name ?? '' }
  })

  async function handleSave() {
    if (!isValid || !loaded) return
    const sign = totalAmount < 0 ? -1 : 1
    const lines = splits.map((s) => ({
      id: s.serverId,
      amount: (expressionToCents(s.amount) / 100) * sign,
      category_id: s.categoryId ?? undefined,
      memo: s.memo || undefined,
    }))
    try {
      // In place either way: the row keeps its identity, receipt, bank link
      // and provenance. (A create-new-and-delete replacement used to drop
      // all of those and turned a pending row into a cleared one.)
      if (txn.is_split) await replaceSplits.mutateAsync({ id: txn.id, splits: lines })
      else await convertToSplit.mutateAsync({ id: txn.id, splits: lines })
      stopSplitEditing()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not save the split'))
    }
  }

  const saving = convertToSplit.isPending || replaceSplits.isPending

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

      {!loaded ? (
        <div className="split-editor__loading" role="status">
          <RefreshCw size={14} className="spin" aria-hidden />
          Loading lines…
        </div>
      ) : (
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
      )}

      <div className="split-editor__footer">
        <button className="split-editor__add-btn" onClick={addSplit} disabled={!loaded}>
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
            disabled={!isValid || !loaded || saving}
          >
            Save Split
          </button>
        </div>
      </div>
    </div>
  )
}
