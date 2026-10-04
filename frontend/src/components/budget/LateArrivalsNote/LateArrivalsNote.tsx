import { useMemo, useState } from 'react'
import { CalendarArrowUp, X } from 'lucide-react'
import { useAccounts } from '../../../api/accounts'
import { useCategories } from '../../../api/categories'
import { usePayees } from '../../../api/payees'
import { useFormatters } from '../../../hooks/useFormatters'
import type { LateArrival } from '../../../types'
import { addMonths, formatMonth } from '../../../utils/dates'
import { dismissedCount, rememberDismissed } from './lateArrivalsDismissal'
import './LateArrivalsNote.css'

interface Props {
  budgetId: string
  /** The import month — where these rows count. */
  month: string
  /** Served: `BudgetMonth.late_arrivals`, non-empty only on the import month. */
  arrivals: LateArrival[]
}

/**
 * The import month's list of late arrivals: rows dated in the month before
 * that reached IGAB after the import and count here (backend
 * `txn_filters.LATE_ARRIVAL`). An envelope that moved for money nobody can
 * see on this month's register is the confusion this answers.
 *
 * Dismissible per device, and back again when more arrive: the count seen is
 * remembered, so a new straggler is news and an old list is not nagging.
 */
export function LateArrivalsNote({ budgetId, month, arrivals }: Props) {
  const { formatMoney, formatDate } = useFormatters()
  const { data: accounts } = useAccounts(budgetId, { includeClosed: true })
  const { data: categories } = useCategories(budgetId, true)
  const { data: payees } = usePayees(budgetId)
  const [dismissed, setDismissed] = useState(() => dismissedCount(budgetId))

  const names = useMemo(
    () => ({
      account: new Map((accounts ?? []).map((a) => [a.id, a.name])),
      category: new Map((categories ?? []).map((c) => [c.id, c.name])),
      payee: new Map((payees ?? []).map((p) => [p.id, p.name])),
    }),
    [accounts, categories, payees]
  )

  if (arrivals.length === 0 || arrivals.length <= dismissed) return null

  const before = formatMonth(addMonths(month, -1))
  const count = arrivals.length
  return (
    <section className="late-arrivals" aria-label="Transactions counted from the month before">
      <div className="late-arrivals__head">
        <CalendarArrowUp size={14} aria-hidden />
        <p className="late-arrivals__lead">
          {count === 1 ? 'One transaction' : `${count} transactions`} dated in {before} arrived
          after your import, so {count === 1 ? 'it counts' : 'they count'} here, in{' '}
          {formatMonth(month)}.
        </p>
        <button
          type="button"
          className="late-arrivals__dismiss"
          aria-label="Dismiss"
          onClick={() => {
            rememberDismissed(budgetId, count)
            setDismissed(count)
          }}
        >
          <X size={14} />
        </button>
      </div>
      <details className="late-arrivals__details">
        <summary>Show {count === 1 ? 'it' : 'them'}</summary>
        <ul className="late-arrivals__list">
          {arrivals.map((a) => (
            <li key={a.transaction_id} className="late-arrivals__row">
              <span className="late-arrivals__date">{formatDate(a.date)}</span>
              <span className="late-arrivals__payee">
                {(a.payee_id && names.payee.get(a.payee_id)) ||
                  names.account.get(a.account_id) ||
                  '—'}
              </span>
              <span className="late-arrivals__category">
                {a.category_id ? (names.category.get(a.category_id) ?? '—') : 'Needs a category'}
              </span>
              <span className="late-arrivals__amount">{formatMoney(a.amount)}</span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
