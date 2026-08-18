import { useState } from 'react'
import { useCategories, useCategoryGroups } from '../../api/categories'
import { useAccounts } from '../../api/accounts'
import { useCreateScheduledTransaction, useUpdateScheduledTransaction, useDeleteScheduledTransaction } from '../../api/scheduledTransactions'
import { today } from '../../utils/dates'
import type { ScheduledTransaction } from '../../types'
import { useFocusTrap } from '../../hooks/useFocusTrap'
import { GroupedCategoryOptions } from '../common/GroupedCategoryOptions/GroupedCategoryOptions'
import './ScheduledTransactionEditor.css'
import { confirmAsync } from '../../stores/confirmStore'

const FREQUENCIES = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Every 2 weeks' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
]

interface InitialValues {
  account_id?: string
  amount?: number
  category_id?: string
  memo?: string
}

interface Props {
  budgetId: string
  existing: ScheduledTransaction | null
  initial?: InitialValues
  onClose: () => void
}

export function ScheduledTransactionEditor({ budgetId, existing, initial, onClose }: Props) {
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: categoryGroups = [] } = useCategoryGroups(budgetId)

  const create = useCreateScheduledTransaction(budgetId)
  const update = useUpdateScheduledTransaction(budgetId)
  const del = useDeleteScheduledTransaction(budgetId)

  const [accountId, setAccountId] = useState(existing?.account_id ?? initial?.account_id ?? '')
  const [amount, setAmount] = useState(
    existing ? String(Math.abs(Number(existing.amount)))
    : initial?.amount ? String(Math.abs(initial.amount))
    : ''
  )
  const [isOutflow, setIsOutflow] = useState(
    existing ? Number(existing.amount) < 0
    : initial?.amount !== undefined ? initial.amount < 0
    : true
  )
  const [frequency, setFrequency] = useState(existing?.frequency ?? 'monthly')
  const [startDate, setStartDate] = useState(existing?.start_date ?? today())
  const [categoryId, setCategoryId] = useState(existing?.category_id ?? initial?.category_id ?? '')
  const [memo, setMemo] = useState(existing?.memo ?? initial?.memo ?? '')
  const [autoCreate, setAutoCreate] = useState(existing?.auto_create ?? false)
  const trapRef = useFocusTrap<HTMLFormElement>(onClose)

  const groupedCategories = categoryGroups
    .filter((g) => !g.is_hidden)
    .map((g) => ({
      group: g,
      cats: categories.filter((c) => c.category_group_id === g.id && !c.is_hidden),
    }))
    .filter((g) => g.cats.length > 0)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const numAmount = parseFloat(amount) || 0
    const finalAmount = isOutflow ? -numAmount : numAmount
    const payload = {
      account_id: accountId,
      amount: finalAmount,
      frequency,
      start_date: startDate,
      category_id: categoryId || undefined,
      memo: memo || undefined,
      auto_create: autoCreate,
    }
    if (existing) {
      await update.mutateAsync({ id: existing.id, ...payload })
    } else {
      await create.mutateAsync(payload)
    }
    onClose()
  }

  async function handleDelete() {
    if (!existing) return
    const ok = await confirmAsync({
      title: 'Delete this scheduled transaction?',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    await del.mutateAsync(existing.id)
    onClose()
  }

  return (
    <div className="sched-editor-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <form
        ref={trapRef}
        tabIndex={-1}
        className="sched-editor"
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal
        aria-labelledby="sched-editor-title"
      >
        <div className="sched-editor__header">
          <span id="sched-editor-title">{existing ? 'Edit Scheduled Transaction' : 'New Scheduled Transaction'}</span>
          <button type="button" onClick={onClose} className="sched-editor__close" aria-label="Close">×</button>
        </div>

        <div className="sched-editor__body">
          <label className="sched-editor__label">
            Account
            <select className="sched-editor__input" value={accountId} onChange={(e) => setAccountId(e.target.value)} required>
              <option value="">Select account…</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>

          <div className="sched-editor__row">
            <label className="sched-editor__label">
              Type
              <select className="sched-editor__input" value={isOutflow ? 'out' : 'in'} onChange={(e) => setIsOutflow(e.target.value === 'out')}>
                <option value="out">Outflow</option>
                <option value="in">Inflow</option>
              </select>
            </label>
            <label className="sched-editor__label">
              Amount
              <input type="number" inputMode="decimal" step="0.01" min="0" className="sched-editor__input" value={amount} onChange={(e) => setAmount(e.target.value)} required />
            </label>
          </div>

          <div className="sched-editor__row">
            <label className="sched-editor__label">
              Frequency
              <select className="sched-editor__input" value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                {FREQUENCIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
            </label>
            <label className="sched-editor__label">
              Start Date
              <input type="date" className="sched-editor__input" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
            </label>
          </div>

          <label className="sched-editor__label">
            Category
            <select className="sched-editor__input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">No category</option>
              <GroupedCategoryOptions groups={groupedCategories} />
            </select>
          </label>

          <label className="sched-editor__label">
            Memo
            <input type="text" className="sched-editor__input" value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="Optional…" />
          </label>

          <label className="sched-editor__label sched-editor__label--inline">
            <input type="checkbox" checked={autoCreate} onChange={(e) => setAutoCreate(e.target.checked)} />
            Auto-create transaction when due
          </label>
        </div>

        <div className="sched-editor__footer">
          {existing ? (
            <button type="button" className="sched-editor__btn sched-editor__btn--danger" onClick={handleDelete}>Delete</button>
          ) : <span />}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="button" className="sched-editor__btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="sched-editor__btn sched-editor__btn--primary">
              {existing ? 'Save' : 'Create'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
