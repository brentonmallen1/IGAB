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
import {
  canRemoveSplitLine,
  checkSplit,
  draftsFromLines,
  mayTakeRemainder,
  takeRemainder,
} from '../../../utils/splits'
import { expressionToCents } from '../../../utils/amountExpression'
import { apiErrorMessage } from '../../../api/client'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { Combobox } from '../../common/Combobox/Combobox'
import { filingCategoryOptions } from '../../../utils/categoryPickers'
import { keepsSelection } from '../../../utils/keepsSelection'
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
  const {
    splitEditing,
    updateSplit,
    addSplit,
    removeSplit,
    stopSplitEditing,
    seedSplits,
    setSplits,
    setSplitTotal,
  } = useTransactionEditStore()
  const convertToSplit = useConvertToSplit(budgetId)
  const replaceSplits = useReplaceSplits(budgetId)

  // An existing split's lines live on the server, never in the loaded page.
  const { data: lines, isError: linesFailed } = useTransactionSplits(txn.id, txn.is_split)
  // `loaded` is a dependency on purpose: a reset back to "awaiting lines"
  // (the editor reopened on this row) must re-seed from the same cached
  // `lines`, which as a reference never changes — without it the editor sat
  // on "Loading lines…" for good.
  const editingThis = splitEditing?.transactionId === txn.id
  const awaitingLines = editingThis && !splitEditing.loaded
  useEffect(() => {
    if (lines && awaitingLines) seedSplits(txn.id, draftsFromLines(lines))
  }, [lines, awaitingLines, txn.id, seedSplits])

  // A saved split's total, as typed. The total used to be a label here and a
  // locked field everywhere else — a split entered as 100 that should have
  // been 108 could only be deleted and re-entered. It is corrected here, with
  // the lines, because the server will not move one without the other.
  // Reconciled: the statement vouched for the amount, so it stays a label.
  const canRetotal = txn.is_split && txn.cleared !== 'reconciled'

  if (!splitEditing || splitEditing.transactionId !== txn.id) return null

  const { totalAmount, totalInput, splits, loaded } = splitEditing
  const savedTotalCents = Math.abs(toCents(totalAmount))
  // NaN while the box holds nothing readable: `checkSplit` refuses that as
  // 'no-total', so an unreadable total can never be saved as zero.
  const totalCents = canRetotal ? expressionToCents(totalInput) : savedTotalCents
  const check = checkSplit(totalCents, splits)
  const { remainingCents, isValid } = check
  const remaining = fromCents(remainingCents)

  // The list every picker that files a leg offers. A split line is a leg
  // like any other.
  const categoryOptions = filingCategoryOptions(categories, categoryGroups)

  async function handleSave() {
    if (!isValid || !loaded) return
    const sign = totalAmount < 0 ? -1 : 1
    const lines = splits.map((s) => ({
      id: s.serverId,
      amount: fromCents(expressionToCents(s.amount)) * sign,
      category_id: s.categoryId ?? undefined,
      memo: s.memo || undefined,
    }))
    try {
      // In place either way: the row keeps its identity, receipt, bank link
      // and provenance. (A create-new-and-delete replacement used to drop
      // all of those and turned a pending row into a cleared one.)
      if (txn.is_split)
        await replaceSplits.mutateAsync({
          id: txn.id,
          accountId: txn.account_id,
          splits: lines,
          // Only a total that actually moved: an unchanged one is not sent,
          // so a plain re-filing of lines stays plain bookkeeping.
          amount: totalCents !== savedTotalCents ? fromCents(totalCents) * sign : undefined,
        })
      else await convertToSplit.mutateAsync({ id: txn.id, splits: lines })
      stopSplitEditing()
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not save the split'))
    }
  }

  const saving = convertToSplit.isPending || replaceSplits.isPending

  return (
    <div className="split-editor" {...keepsSelection}>
      <div className="split-editor__header">
        {canRetotal ? (
          <label className="split-editor__title split-editor__total">
            Split total
            <AmountInput
              className="split-editor__amount split-editor__total-input"
              value={totalInput}
              onValueChange={setSplitTotal}
              placeholder="Total"
              aria-label="Split total"
            />
          </label>
        ) : (
          <span className="split-editor__title">
            Split <strong>{formatMoney(Math.abs(totalAmount))}</strong>
          </span>
        )}
        <button
          className="split-editor__close"
          onClick={stopSplitEditing}
          aria-label="Cancel split"
          title="Cancel"
        >
          <X size={14} />
        </button>
      </div>

      {!loaded && linesFailed ? (
        <div className="split-editor__loading split-editor__loading--error" role="alert">
          This split’s lines could not be loaded. Cancel and try again.
        </div>
      ) : !loaded ? (
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

              {/* Put what is left on this line — or take what is over off it.
                  The slot is always there, so the row does not jump as the
                  lines come into balance. */}
              <span className="split-editor__rest-slot">
                {mayTakeRemainder(split, remainingCents) && (
                  <button
                    type="button"
                    className="split-editor__rest tabular"
                    onClick={() => setSplits(takeRemainder(splits, remainingCents, i))}
                    title={
                      remainingCents > 0
                        ? `Put the remaining ${formatMoney(remaining)} on this line`
                        : `Take the extra ${formatMoney(-remaining)} off this line`
                    }
                    aria-label={
                      remainingCents > 0
                        ? `Put the remaining ${formatMoney(remaining)} on line ${i + 1}`
                        : `Take the extra ${formatMoney(-remaining)} off line ${i + 1}`
                    }
                  >
                    {remainingCents > 0 ? '+' : '−'}
                    {formatMoney(Math.abs(remaining))}
                  </button>
                )}
              </span>

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
                disabled={!canRemoveSplitLine(splits.length)}
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

        <div
          className={`split-editor__remaining ${remainingCents === 0 ? 'split-editor__remaining--done' : ''}`}
        >
          {check.reason === 'no-total'
            ? 'Enter the total'
            : remainingCents === 0
              ? 'Fully assigned'
              : remainingCents > 0
                ? `Remaining: ${formatMoney(remaining)}`
                : `Over by ${formatMoney(-remaining)}`}
        </div>

        <div className="split-editor__actions">
          <button className="split-editor__cancel" onClick={stopSplitEditing}>
            Cancel
          </button>
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
