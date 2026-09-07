import { parseAmountInput } from '../../utils/money'
import { groupedCategorySections } from '../../utils/categoryPickers'
import { useState } from 'react'
import { useCategories, useCategoryGroups } from '../../api/categories'
import { useAccounts } from '../../api/accounts'
import {
  useCreateScheduledTransaction,
  useUpdateScheduledTransaction,
  useDeleteScheduledTransaction,
  type ScheduledTransactionCreate,
  type ScheduledTransactionUpdate,
} from '../../api/scheduledTransactions'
import { today } from '../../utils/dates'
import { FREQUENCIES } from '../../utils/schedule'
import type { ScheduledTransaction } from '../../types'
import { useFocusTrap } from '../../hooks/useFocusTrap'
import { GroupedCategoryOptions } from '../common/GroupedCategoryOptions/GroupedCategoryOptions'
import './ScheduledTransactionEditor.css'
import { confirmAsync } from '../../stores/confirmStore'
import { apiErrorMessage } from '../../api/client'

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
    existing
      ? String(Math.abs(existing.amount))
      : initial?.amount
        ? String(Math.abs(initial.amount))
        : ''
  )
  const [isOutflow, setIsOutflow] = useState(
    existing ? existing.amount < 0 : initial?.amount !== undefined ? initial.amount < 0 : true
  )
  const [frequency, setFrequency] = useState(existing?.frequency ?? 'monthly')
  const [startDate, setStartDate] = useState(existing?.start_date ?? today())
  const [endDate, setEndDate] = useState(existing?.end_date ?? '')
  const [secondDay, setSecondDay] = useState(
    existing?.second_day_of_month != null ? String(existing.second_day_of_month) : ''
  )
  // A schedule is a transfer or it files into a category; both is what the
  // register allows for a transfer to a tracking account, so the picker
  // clears the category when a transfer target is chosen but does not
  // forbid re-adding one.
  const [transferTo, setTransferTo] = useState(existing?.transfer_account_id ?? '')
  const [categoryId, setCategoryId] = useState(existing?.category_id ?? initial?.category_id ?? '')
  const [memo, setMemo] = useState(existing?.memo ?? initial?.memo ?? '')
  const [autoCreate, setAutoCreate] = useState(existing?.auto_create ?? false)
  const [reminderDays, setReminderDays] = useState(String(existing?.days_before_reminder ?? 3))
  const [error, setError] = useState<string | null>(null)
  const trapRef = useFocusTrap<HTMLFormElement>(onClose)

  // Was `!is_archived` alone, which offered credit-card payment categories that
  // no other surface does.
  const groupedCategories = groupedCategorySections(
    categories.filter((c) => c.is_categorizable),
    categoryGroups
  )
  const transferTargets = accounts.filter((a) => a.id !== accountId)
  const isTwiceMonthly = frequency === 'twice_monthly'
  const isOnce = frequency === 'once'

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Was `parseFloat(amount) || 0`, which scheduled a recurring $0.00
    // transaction whenever the amount could not be read — including every
    // "1.234,56" on a decimal-comma locale that utils/money supports.
    const numAmount = parseAmountInput(amount)
    if (isNaN(numAmount) || numAmount <= 0) {
      setError('Enter an amount.')
      return
    }
    const secondDayNum = isTwiceMonthly ? Number(secondDay) : null
    if (isTwiceMonthly && (!secondDay || !Number.isInteger(secondDayNum) || secondDayNum! < 1)) {
      setError('Enter the second day of the month (1–31).')
      return
    }
    const reminder = Number(reminderDays)
    if (!Number.isInteger(reminder) || reminder < 0) {
      setError('Reminder days must be a whole number.')
      return
    }
    setError(null)
    const finalAmount = isOutflow ? -numAmount : numAmount
    try {
      if (existing) {
        // null, not undefined: the PATCH treats an omitted field as untouched
        // and an explicit null as "clear it".
        const payload: ScheduledTransactionUpdate & { id: string } = {
          id: existing.id,
          account_id: accountId,
          amount: finalAmount,
          frequency,
          start_date: startDate,
          end_date: isOnce ? null : endDate || null,
          second_day_of_month: isTwiceMonthly ? secondDayNum : null,
          transfer_account_id: transferTo || null,
          category_id: categoryId || null,
          memo: memo || null,
          auto_create: autoCreate,
          days_before_reminder: reminder,
        }
        await update.mutateAsync(payload)
      } else {
        const payload: ScheduledTransactionCreate = {
          account_id: accountId,
          amount: finalAmount,
          frequency,
          start_date: startDate,
          end_date: !isOnce && endDate ? endDate : undefined,
          second_day_of_month: isTwiceMonthly ? (secondDayNum ?? undefined) : undefined,
          transfer_account_id: transferTo || undefined,
          category_id: categoryId || undefined,
          memo: memo || undefined,
          auto_create: autoCreate,
          days_before_reminder: reminder,
        }
        await create.mutateAsync(payload)
      }
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save the schedule'))
    }
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
    <div
      className="sched-editor-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
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
          <span id="sched-editor-title">
            {existing ? 'Edit Scheduled Transaction' : 'New Scheduled Transaction'}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="sched-editor__close"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="sched-editor__body">
          <label className="sched-editor__label">
            Account
            <select
              className="sched-editor__input"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              required
            >
              <option value="">Select account…</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>

          <div className="sched-editor__row">
            <label className="sched-editor__label">
              Type
              <select
                className="sched-editor__input"
                value={isOutflow ? 'out' : 'in'}
                onChange={(e) => setIsOutflow(e.target.value === 'out')}
              >
                <option value="out">Outflow</option>
                <option value="in">Inflow</option>
              </select>
            </label>
            <label className="sched-editor__label">
              Amount
              <input
                type="number"
                inputMode="decimal"
                step="0.01"
                min="0"
                className="sched-editor__input"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            </label>
          </div>

          <div className="sched-editor__row">
            <label className="sched-editor__label">
              Frequency
              <select
                className="sched-editor__input"
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
              >
                {FREQUENCIES.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="sched-editor__label">
              {isOnce ? 'Date' : 'Start Date'}
              <input
                type="date"
                className="sched-editor__input"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                required
              />
            </label>
          </div>

          {isTwiceMonthly && (
            <label className="sched-editor__label">
              Second day of the month
              <input
                type="number"
                inputMode="numeric"
                min="1"
                max="31"
                step="1"
                className="sched-editor__input"
                value={secondDay}
                onChange={(e) => setSecondDay(e.target.value)}
                placeholder="e.g. 15 — the first is the start date's day"
                required
              />
            </label>
          )}

          {!isOnce && (
            <label className="sched-editor__label">
              End Date
              <input
                type="date"
                className="sched-editor__input"
                value={endDate}
                min={startDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </label>
          )}

          <label className="sched-editor__label">
            Transfer to
            <select
              className="sched-editor__input"
              value={transferTo}
              onChange={(e) => {
                setTransferTo(e.target.value)
                if (e.target.value) setCategoryId('')
              }}
            >
              <option value="">Not a transfer</option>
              {transferTargets.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>

          <label className="sched-editor__label">
            Category
            <select
              className="sched-editor__input"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
            >
              <option value="">No category</option>
              <GroupedCategoryOptions groups={groupedCategories} />
            </select>
          </label>

          <label className="sched-editor__label">
            Memo
            <input
              type="text"
              className="sched-editor__input"
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              placeholder="Optional…"
            />
          </label>

          <div className="sched-editor__row">
            <label className="sched-editor__label">
              Remind days before
              <input
                type="number"
                inputMode="numeric"
                min="0"
                step="1"
                className="sched-editor__input"
                value={reminderDays}
                onChange={(e) => setReminderDays(e.target.value)}
              />
            </label>
            <label className="sched-editor__label sched-editor__label--inline">
              <input
                type="checkbox"
                checked={autoCreate}
                onChange={(e) => setAutoCreate(e.target.checked)}
              />
              Auto-create transaction when due
            </label>
          </div>
        </div>

        <div className="sched-editor__footer">
          {existing ? (
            <button
              type="button"
              className="sched-editor__btn sched-editor__btn--danger"
              onClick={handleDelete}
            >
              Delete
            </button>
          ) : (
            <span />
          )}
          {error && (
            <div className="sched-editor__error" role="alert">
              {error}
            </div>
          )}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="button" className="sched-editor__btn" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="sched-editor__btn sched-editor__btn--primary">
              {existing ? 'Save' : 'Create'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
