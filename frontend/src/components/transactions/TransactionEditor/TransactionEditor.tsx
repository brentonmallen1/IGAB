import { useState, useRef, useEffect } from 'react'
import { X, Trash2, Sparkles, Split, Plus } from 'lucide-react'
import {
  useCreateTransaction,
  useUpdateTransaction,
  useDeleteTransaction,
  usePayees,
} from '../../../api/transactions'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useAccounts } from '../../../api/accounts'
import { useSuggestCategory } from '../../../api/ai'
import { today } from '../../../utils/dates'
import type { Transaction, Payee } from '../../../types'
import type { SplitDraft } from '../../../stores/transactionEditStore'
import './TransactionEditor.css'

interface Props {
  budgetId: string
  accountId: string
  transaction: Transaction | null
  onClose: () => void
}

export function TransactionEditor({ budgetId, accountId, transaction, onClose }: Props) {
  const createTxn = useCreateTransaction(budgetId)
  const updateTxn = useUpdateTransaction(budgetId)
  const deleteTxn = useDeleteTransaction(budgetId)
  const suggestCategory = useSuggestCategory(budgetId)

  const { data: payees = [] } = usePayees(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)

  const isEdit = !!transaction

  const [date, setDate] = useState(transaction?.date.slice(0, 10) ?? today())
  const [payeeQuery, setPayeeQuery] = useState('')
  const [selectedPayeeId, setSelectedPayeeId] = useState<string | null>(
    transaction?.payee_id ?? null
  )
  const [categoryId, setCategoryId] = useState(transaction?.category_id ?? '')
  const [memo, setMemo] = useState(transaction?.memo ?? '')
  const [outflow, setOutflow] = useState(() => {
    if (!transaction || Number(transaction.amount) >= 0) return ''
    return String(Math.abs(Number(transaction.amount)))
  })
  const [inflow, setInflow] = useState(() => {
    if (!transaction || Number(transaction.amount) < 0) return ''
    return String(Number(transaction.amount))
  })
  const [cleared, setCleared] = useState<'uncleared' | 'cleared' | 'reconciled'>(
    (transaction?.cleared === 'pending' ? 'uncleared' : transaction?.cleared) ?? 'uncleared'
  )
  const [isTransfer, setIsTransfer] = useState(!!transaction?.transfer_id)
  const [transferAccountId, setTransferAccountId] = useState('')
  const [showPayeeDropdown, setShowPayeeDropdown] = useState(false)
  const [isSplit, setIsSplit] = useState(false)
  const [splits, setSplits] = useState<SplitDraft[]>([
    { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' },
    { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' },
  ])

  const payeeRef = useRef<HTMLDivElement>(null)
  const payeeInitialized = useRef(false)

  // Initialize payee query once payees are loaded (edit mode)
  useEffect(() => {
    if (!payeeInitialized.current && transaction?.payee_id && payees.length > 0) {
      const p = payees.find((p) => p.id === transaction.payee_id)
      if (p) {
        setPayeeQuery(p.name)
        payeeInitialized.current = true
      }
    }
  }, [payees, transaction?.payee_id])

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (payeeRef.current && !payeeRef.current.contains(e.target as Node)) {
        setShowPayeeDropdown(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filteredPayees = payeeQuery.length > 0
    ? payees.filter((p) => p.name.toLowerCase().includes(payeeQuery.toLowerCase())).slice(0, 8)
    : payees.slice(0, 8)

  const groupedCategories = categoryGroups
    .filter((g) => !g.is_hidden)
    .map((g) => ({
      group: g,
      cats: categories.filter(
        (c) => c.category_group_id === g.id && !c.is_hidden && !c.linked_account_id
      ),
    }))
    .filter((g) => g.cats.length > 0)

  const transferAccounts = accounts.filter((a) => a.id !== accountId)

  function handlePayeeSelect(p: Payee) {
    setPayeeQuery(p.name)
    setSelectedPayeeId(p.id)
    setShowPayeeDropdown(false)
    if (p.default_category_id && !categoryId) {
      setCategoryId(p.default_category_id)
    }
  }

  function handlePayeeChange(e: React.ChangeEvent<HTMLInputElement>) {
    setPayeeQuery(e.target.value)
    setSelectedPayeeId(null)
    setShowPayeeDropdown(true)
  }

  function handleOutflowChange(e: React.ChangeEvent<HTMLInputElement>) {
    setOutflow(e.target.value)
    if (e.target.value) setInflow('')
  }

  function handleInflowChange(e: React.ChangeEvent<HTMLInputElement>) {
    setInflow(e.target.value)
    if (e.target.value) setOutflow('')
  }

  function updateSplit(tempId: string, data: Partial<Omit<SplitDraft, 'tempId'>>) {
    setSplits((prev) => prev.map((s) => s.tempId === tempId ? { ...s, ...data } : s))
  }

  function addSplit() {
    setSplits((prev) => [...prev, { tempId: crypto.randomUUID(), amount: '', categoryId: null, memo: '' }])
  }

  function removeSplit(tempId: string) {
    setSplits((prev) => prev.length > 2 ? prev.filter((s) => s.tempId !== tempId) : prev)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const outflowVal = parseFloat(outflow) || 0
    const inflowVal = parseFloat(inflow) || 0
    const amount = outflowVal > 0 ? -outflowVal : inflowVal
    const sign = amount < 0 ? -1 : 1

    if (isSplit && !isTransfer) {
      const splitPayload = {
        account_id: accountId,
        date,
        amount,
        memo: memo || undefined,
        cleared,
        approved: true,
        payee_id: selectedPayeeId || undefined,
        payee_name: !selectedPayeeId && payeeQuery ? payeeQuery : undefined,
        splits: splits.map((s) => ({
          amount: parseFloat(s.amount) * sign,
          category_id: s.categoryId ?? undefined,
          memo: s.memo || undefined,
        })),
      }
      await createTxn.mutateAsync(splitPayload)
      onClose()
      return
    }

    const payload = {
      account_id: accountId,
      date,
      amount,
      memo: memo || undefined,
      cleared,
      approved: true,
      ...(isTransfer
        ? { transfer_account_id: transferAccountId }
        : {
            payee_id: selectedPayeeId || undefined,
            payee_name: !selectedPayeeId && payeeQuery ? payeeQuery : undefined,
            category_id: categoryId || undefined,
          }),
    }

    if (isEdit) {
      await updateTxn.mutateAsync({ id: transaction!.id, ...payload })
    } else {
      await createTxn.mutateAsync(payload)
    }
    onClose()
  }

  async function handleDelete() {
    if (!transaction) return
    if (!confirm('Delete this transaction?')) return
    await deleteTxn.mutateAsync({ id: transaction.id, accountId })
    onClose()
  }

  const isPending = createTxn.isPending || updateTxn.isPending || deleteTxn.isPending

  const splitIsValid = (() => {
    if (!isSplit) return true
    const totalAmt = Math.abs((parseFloat(outflow) || 0) || (parseFloat(inflow) || 0))
    const splitTotal = splits.reduce((sum, s) => sum + (parseFloat(s.amount) || 0), 0)
    return Math.abs(splitTotal - totalAmt) < 0.01 && splits.every((s) => s.categoryId && parseFloat(s.amount) > 0)
  })()

  return (
    <div
      className="txn-editor-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <form className="txn-editor" role="dialog" aria-modal onSubmit={handleSubmit}>
        <div className="txn-editor__header">
          <span className="txn-editor__title">
            {isEdit ? 'Edit Transaction' : 'Add Transaction'}
          </span>
          <button type="button" className="txn-editor__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="txn-editor__body">
          <div className="txn-editor__row">
            <div className="txn-editor__field">
              <label className="txn-editor__label">Date</label>
              <input
                type="date"
                className="txn-editor__input"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div className="txn-editor__field">
              <label className="txn-editor__label">Cleared</label>
              <select
                className="txn-editor__select"
                value={cleared}
                onChange={(e) => setCleared(e.target.value as typeof cleared)}
              >
                <option value="uncleared">Uncleared</option>
                <option value="cleared">Cleared</option>
                <option value="reconciled">Reconciled</option>
              </select>
            </div>
          </div>

          <div className="txn-editor__field">
            <label className="txn-editor__label">Payee</label>
            <div className="txn-editor__payee-wrap" ref={payeeRef}>
              <input
                type="text"
                className="txn-editor__input"
                value={payeeQuery}
                onChange={handlePayeeChange}
                onFocus={() => setShowPayeeDropdown(true)}
                placeholder="Search or enter payee..."
                autoComplete="off"
              />
              {showPayeeDropdown && filteredPayees.length > 0 && (
                <div className="txn-editor__payee-dropdown">
                  {filteredPayees.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="txn-editor__payee-option"
                      onMouseDown={() => handlePayeeSelect(p)}
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="txn-editor__toggle-row">
            <label className="txn-editor__toggle" aria-label="Transfer to account">
              <input
                type="checkbox"
                checked={isTransfer}
                onChange={(e) => setIsTransfer(e.target.checked)}
              />
              <span className="txn-editor__toggle-slider" />
            </label>
            <span className="txn-editor__toggle-label">Transfer to account</span>
          </div>

          {isTransfer ? (
            <div className="txn-editor__field">
              <label className="txn-editor__label">To Account</label>
              <select
                className="txn-editor__select"
                value={transferAccountId}
                onChange={(e) => setTransferAccountId(e.target.value)}
                required={isTransfer}
              >
                <option value="">Select account…</option>
                {transferAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>
          ) : isSplit ? (
            <div className="txn-editor__field">
              <label className="txn-editor__label">
                Split Transaction
                <button
                  type="button"
                  className="txn-editor__ai-btn"
                  onClick={() => { setIsSplit(false); setCategoryId('') }}
                  title="Switch to single category"
                >
                  <X size={12} />
                  Cancel split
                </button>
              </label>
              <div className="txn-editor__splits">
                {splits.map((s) => (
                  <div key={s.tempId} className="txn-editor__split-row">
                    <select
                      className="txn-editor__select txn-editor__split-category"
                      value={s.categoryId ?? ''}
                      onChange={(e) => updateSplit(s.tempId, { categoryId: e.target.value || null })}
                    >
                      <option value="">Category…</option>
                      {groupedCategories.map(({ group, cats }) => (
                        <optgroup key={group.id} label={group.name}>
                          {cats.map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                    <input
                      className="txn-editor__input txn-editor__split-amount"
                      type="number"
                      min="0"
                      step="0.01"
                      value={s.amount}
                      onChange={(e) => updateSplit(s.tempId, { amount: e.target.value })}
                      placeholder="0.00"
                    />
                    <button
                      type="button"
                      className="txn-editor__split-remove"
                      onClick={() => removeSplit(s.tempId)}
                      disabled={splits.length <= 2}
                      title="Remove"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
                <div className="txn-editor__split-footer">
                  <button type="button" className="txn-editor__split-add" onClick={addSplit}>
                    <Plus size={12} /> Add split
                  </button>
                  {(() => {
                    const splitTotal = splits.reduce((sum, s) => sum + (parseFloat(s.amount) || 0), 0)
                    const totalAmt = Math.abs((parseFloat(outflow) || 0) || (parseFloat(inflow) || 0))
                    const remaining = totalAmt - splitTotal
                    return (
                      <span className={`txn-editor__split-remaining ${Math.abs(remaining) < 0.01 ? 'txn-editor__split-remaining--done' : ''}`}>
                        {Math.abs(remaining) < 0.01 ? 'Fully assigned' : `Remaining: $${remaining.toFixed(2)}`}
                      </span>
                    )
                  })()}
                </div>
              </div>
            </div>
          ) : (
            <div className="txn-editor__field">
              <label className="txn-editor__label">
                Category
                <button
                  type="button"
                  className="txn-editor__ai-btn"
                  title="Split this transaction"
                  onClick={() => setIsSplit(true)}
                >
                  <Split size={12} />
                  Split
                </button>
                <button
                  type="button"
                  className="txn-editor__ai-btn"
                  title="AI suggest category"
                  disabled={suggestCategory.isPending}
                  onClick={async () => {
                    const outflowVal = parseFloat(outflow) || 0
                    const inflowVal = parseFloat(inflow) || 0
                    const amount = outflowVal > 0 ? -outflowVal : inflowVal
                    const result = await suggestCategory.mutateAsync({
                      payee_name: payeeQuery || 'Unknown',
                      amount,
                      memo: memo || undefined,
                    })
                    if (result.category_id) setCategoryId(result.category_id)
                  }}
                >
                  <Sparkles size={12} />
                  {suggestCategory.isPending ? 'Thinking…' : 'AI Suggest'}
                </button>
              </label>
              <select
                className="txn-editor__select"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
              >
                <option value="">No category</option>
                {groupedCategories.map(({ group, cats }) => (
                  <optgroup key={group.id} label={group.name}>
                    {cats.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          )}

          <div className="txn-editor__field">
            <label className="txn-editor__label">Memo</label>
            <input
              type="text"
              className="txn-editor__input"
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              placeholder="Optional note..."
            />
          </div>

          <div className="txn-editor__row">
            <div className="txn-editor__field">
              <label className="txn-editor__label">Outflow</label>
              <input
                type="number"
                className="txn-editor__input"
                value={outflow}
                onChange={handleOutflowChange}
                min="0"
                step="0.01"
                placeholder="0.00"
              />
            </div>
            <div className="txn-editor__field">
              <label className="txn-editor__label">Inflow</label>
              <input
                type="number"
                className="txn-editor__input"
                value={inflow}
                onChange={handleInflowChange}
                min="0"
                step="0.01"
                placeholder="0.00"
              />
            </div>
          </div>
        </div>

        <div className="txn-editor__footer">
          {isEdit ? (
            <button
              type="button"
              className="txn-editor__btn txn-editor__btn--danger"
              onClick={handleDelete}
              disabled={isPending}
            >
              <Trash2 size={14} />
              Delete
            </button>
          ) : (
            <span />
          )}
          <div className="txn-editor__footer-actions">
            <button
              type="button"
              className="txn-editor__btn txn-editor__btn--secondary"
              onClick={onClose}
              disabled={isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="txn-editor__btn txn-editor__btn--primary"
              disabled={isPending || !splitIsValid}
            >
              {isEdit ? 'Save' : 'Add'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
