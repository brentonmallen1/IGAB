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
import { Dialog } from '../common/Dialog/Dialog'
import { GroupedCategoryOptions } from '../common/GroupedCategoryOptions/GroupedCategoryOptions'
import { confirmAsync } from '../../stores/confirmStore'
import { apiErrorMessage } from '../../api/client'

/** The form lives in the scroll region; its submit button lives in the pinned
 *  footer, and `form=` is what joins them. */
const FORM_ID = 'sched-editor-form'

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

  // Was `!is_archived` alone, which offered credit-card payment categories that
  // no other surface does.
  const groupedCategories = groupedCategorySections(
    categories.filter((c) => c.is_categorizable),
    categoryGroups
  )
  const transferTargets = accounts.filter((a) => a.id !== accountId)
  const isTwiceMonthly = frequency === 'twice_monthly'
  const isOnce = frequency === 'once'

  const isPending = create.isPending || update.isPending

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Checked here rather than by `required`: the browser's bubble points at
    // a field the footer's button is not beside, and says nothing on a phone.
    if (!accountId) {
      setError('Choose the account this schedule posts to.')
      return
    }
    // Was `parseFloat(amount) || 0`, which scheduled a recurring $0.00
    // transaction whenever the amount could not be read — including every
    // "1.234,56" on a decimal-comma locale that utils/money supports.
    const numAmount = parseAmountInput(amount)
    if (isNaN(numAmount) || numAmount <= 0) {
      setError('Enter an amount.')
      return
    }
    if (!startDate) {
      setError(isOnce ? 'Enter the date.' : 'Enter the start date.')
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
    <Dialog
      title={existing ? 'Edit scheduled transaction' : 'New scheduled transaction'}
      onClose={onClose}
      historyKey="scheduled-editor"
      footer={
        <div className="dialog-actions">
          {existing && (
            <button type="button" className="dialog-btn dialog-btn--danger" onClick={handleDelete}>
              Delete
            </button>
          )}
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            {/* The footer is pinned outside the form, so the submit button
                reaches it by id rather than by containment. */}
            <button
              type="submit"
              form={FORM_ID}
              className="dialog-btn dialog-btn--primary"
              disabled={isPending}
            >
              {isPending ? 'Saving…' : existing ? 'Save' : 'Create'}
            </button>
          </div>
        </div>
      }
    >
      <form id={FORM_ID} className="dialog-form" onSubmit={handleSubmit} noValidate>
        <label className="dialog-form__field">
          <span>Account</span>
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Select account…</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>

        <div className="dialog-form__row">
          <label className="dialog-form__field">
            <span>Type</span>
            <select
              value={isOutflow ? 'out' : 'in'}
              onChange={(e) => setIsOutflow(e.target.value === 'out')}
            >
              <option value="out">Outflow</option>
              <option value="in">Inflow</option>
            </select>
          </label>
          <label className="dialog-form__field">
            <span>Amount</span>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
        </div>

        <div className="dialog-form__row">
          <label className="dialog-form__field">
            <span>Frequency</span>
            <select value={frequency} onChange={(e) => setFrequency(e.target.value)}>
              {FREQUENCIES.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <label className="dialog-form__field">
            <span>{isOnce ? 'Date' : 'Start date'}</span>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </label>
        </div>

        {isTwiceMonthly && (
          <label className="dialog-form__field">
            <span>Second day of the month</span>
            <input
              type="number"
              inputMode="numeric"
              min="1"
              max="31"
              step="1"
              value={secondDay}
              onChange={(e) => setSecondDay(e.target.value)}
              placeholder="e.g. 15 — the first is the start date's day"
            />
          </label>
        )}

        {!isOnce && (
          <label className="dialog-form__field">
            <span>End date</span>
            <input
              type="date"
              value={endDate}
              min={startDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
        )}

        <label className="dialog-form__field">
          <span>Transfer to</span>
          <select
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

        <label className="dialog-form__field">
          <span>Category</span>
          <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">No category</option>
            <GroupedCategoryOptions groups={groupedCategories} />
          </select>
        </label>

        <label className="dialog-form__field">
          <span>Memo</span>
          <input
            type="text"
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="Optional…"
          />
        </label>

        <label className="dialog-form__field">
          <span>Remind days before</span>
          <input
            type="number"
            inputMode="numeric"
            min="0"
            step="1"
            value={reminderDays}
            onChange={(e) => setReminderDays(e.target.value)}
          />
        </label>
        <label className="dialog-form__field dialog-form__field--inline">
          <input
            type="checkbox"
            checked={autoCreate}
            onChange={(e) => setAutoCreate(e.target.checked)}
          />
          <span>Auto-create transaction when due</span>
        </label>
      </form>
    </Dialog>
  )
}
