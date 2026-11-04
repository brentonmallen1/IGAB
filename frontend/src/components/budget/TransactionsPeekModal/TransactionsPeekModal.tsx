import { useMemo, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, ChevronLeft, Plus, X } from 'lucide-react'
import {
  usePayees,
  useTransactionsPeek,
  useTransactionsPeekMonths,
} from '../../../api/transactions'
import { useAccounts } from '../../../api/accounts'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { Modal } from '../../common/Modal/Modal'
import { transactionDisplayPayee } from '../../../utils/transferDisplay'
import type { Transaction } from '../../../types'
import './TransactionsPeekModal.css'
import { openAccounts } from '../../../utils/accountLists'
import { useCategories } from '../../../api/categories'
import { figureClass, signTone } from '../../../utils/figureTone'
import { CardReserveSummary } from './CardReserveSummary'
import { addMonths } from '../../../utils/dates'
import { sumAmounts } from '../../../utils/money'
import { monthFloor, useAppStore } from '../../../stores/appStore'

const RECENT_LIMIT = 10
const ALL_LIMIT = 1000

/** What the peek is about: one category across accounts (the grid's
 *  Activity click), one account whole (the cards strip's Transactions), or
 *  what set a card's money aside in one month (the strip's Covered and Set
 *  aside figures).
 *
 *  A `month` ("YYYY-MM-01") opens on the rows that month's figure counts —
 *  by the month a row counts in for budget math, not its calendar date (see
 *  `useTransactionsPeek`). */
export type PeekScope =
  | { kind: 'category'; categoryId: string; categoryName: string; month?: string }
  | { kind: 'account'; accountId: string; accountName: string }
  | { kind: 'card-reserve'; accountId: string; accountName: string; month: string }

interface Props {
  budgetId: string
  scope: PeekScope
  onClose: () => void
  /** Optional hand-off into the add-transaction flow (category scope). */
  onAddTransaction?: () => void
}

/**
 * Budget-page drill-in: the most recent transactions for one category across
 * all accounts (narrowable to a single account), or for one account whole.
 * "View all" expands the list in place so the user stays in the budget
 * context; a card's reserve steps back a month at a time instead, since a
 * statement cycle spans two. Clicking rows selects them and the footer totals
 * the selection; each row's arrow opens it in the account register, and
 * "Open in Transactions" hands the same filter to the all-accounts register.
 *
 * On the shared `Modal`, which is load-bearing rather than tidy. This drew
 * its own fixed overlay — the seventh copy of `.overlay`, exactly the one
 * `Dialog`'s docstring warned about — and an inline overlay is not portalled,
 * so it stayed in the page's stacking context. Opened from inside a dialog
 * that IS portalled (the hero's "Overspending on cards"), it rendered behind
 * the thing that raised it at the same z-index, and the only way out looked
 * like closing everything. `Modal` portals to `document.body` and pushes onto
 * the overlay stack, so the newest overlay paints on top and Escape closes
 * only that one.
 */
export function TransactionsPeekModal({ budgetId, scope, onClose, onAddTransaction }: Props) {
  const [accountFilter, setAccountFilter] = useState('')
  const [showAll, setShowAll] = useState(false)
  // Earlier budget months shown under a card's reserve, newest first.
  const [monthsBack, setMonthsBack] = useState(0)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const floor = useAppStore((s) => monthFloor(s))
  const navigate = useNavigate()
  const setTransactionSearch = useUIStore((s) => s.setTransactionSearch)
  const { formatMoney, formatMoneyOrDash, formatDate, formatMonth } = useFormatters()

  // The whole month, not "so far": Activity counts a future-dated row later
  // this month, so the list behind the number has to show it too. A card's
  // reserve is a month's figure through and through, so that list never
  // widens to "all".
  const reserve = scope.kind === 'card-reserve'
  const month = scope.kind === 'account' ? undefined : scope.month
  const budgetMonth = month && (reserve || !showAll) ? month : null
  const { data, isPending } = useTransactionsPeek(
    budgetId,
    scope.kind === 'category'
      ? { categoryId: scope.categoryId, accountId: accountFilter || null }
      : { accountId: scope.accountId, cardReserving: reserve },
    showAll || budgetMonth ? ALL_LIMIT : RECENT_LIMIT,
    budgetMonth
  )
  const earlierMonths = useMemo(
    () =>
      reserve && month
        ? Array.from({ length: monthsBack }, (_, i) => addMonths(month, -(i + 1)))
        : [],
    [reserve, month, monthsBack]
  )
  const earlier = useTransactionsPeekMonths(
    budgetId,
    reserve ? { accountId: scope.accountId, cardReserving: true } : {},
    ALL_LIMIT,
    earlierMonths
  )
  const nextEarlier = reserve && month ? addMonths(month, -(monthsBack + 1)) : null
  const canStepBack = nextEarlier !== null && (floor === null || nextEarlier >= floor)
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: payees = [] } = usePayees(budgetId)
  // Archived envelopes included: one still reserves on a card, and its rows
  // still need a name.
  const { data: categories = [] } = useCategories(reserve ? budgetId : null, true)

  const accountName = useMemo(() => new Map(accounts.map((a) => [a.id, a.name])), [accounts])
  const payeeName = useMemo(() => new Map(payees.map((p) => [p.id, p.name])), [payees])
  const categoryName = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories])
  const title = scope.kind === 'category' ? scope.categoryName : scope.accountName

  const transactions = data?.transactions ?? []
  const totalCount = data?.total_count ?? 0
  // Served per row, never accumulated here. Empty for a category scope.
  const running = data?.running_balances ?? {}
  const showRunning = scope.kind === 'account' && Object.keys(running).length > 0

  // The total covers only rows on screen: a selection made before the list
  // changed under it would otherwise count rows nobody can see.
  const listed = [...transactions, ...earlier.flatMap((q) => q.data?.transactions ?? [])]
  const picked = listed.filter((t) => selected.has(t.id))
  const pickedTotal = sumAmounts(picked.map((t) => t.amount))

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function onRowKey(e: KeyboardEvent<HTMLTableRowElement>, id: string) {
    // The row's own keys only: Enter on its arrow button opens the register.
    if (e.target !== e.currentTarget || (e.key !== 'Enter' && e.key !== ' ')) return
    e.preventDefault()
    toggle(id)
  }

  function describePayee(t: Transaction): string {
    const display = transactionDisplayPayee(t, payeeName, accountName)
    if (display !== '—') return display
    return t.import_description ?? '—'
  }

  function openInRegister(t: Transaction) {
    onClose()
    // The register lists parents only: a split leg is found by its parent row.
    navigate(`/accounts/${t.account_id}?highlight=${t.parent_transaction_id ?? t.id}`)
  }

  function openInTransactions() {
    // Land on the all-accounts register pre-filtered to this peek's scope
    // via the shared search-token state
    if (scope.kind !== 'category') {
      setTransactionSearch(`account:"${scope.accountName}"`)
    } else {
      const accountToken = accountFilter ? ` account:"${accountName.get(accountFilter) ?? ''}"` : ''
      setTransactionSearch(`category:"${scope.categoryName}"${accountToken}`)
    }
    onClose()
    navigate('/transactions')
  }

  function renderTable(rows: Transaction[]) {
    return (
      <table className="category-txns__table">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Payee</th>
            {scope.kind === 'category' && <th scope="col">Account</th>}
            {reserve && <th scope="col">Category</th>}
            <th scope="col" className="category-txns__amount-col">
              Amount
            </th>
            {showRunning && (
              <th scope="col" className="category-txns__amount-col">
                Balance
              </th>
            )}
            <th scope="col" className="category-txns__open-col" aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr
              key={t.id}
              tabIndex={0}
              aria-selected={selected.has(t.id)}
              className={selected.has(t.id) ? 'category-txns__row--selected' : undefined}
              onClick={() => toggle(t.id)}
              onKeyDown={(e) => onRowKey(e, t.id)}
              title="Select to total"
            >
              <td className="category-txns__date">{formatDate(t.date)}</td>
              <td className="category-txns__payee">
                <span className="category-txns__payee-name">{describePayee(t)}</span>
                {t.memo && <span className="category-txns__memo">{t.memo}</span>}
              </td>
              {scope.kind === 'category' && (
                <td className="category-txns__account">{accountName.get(t.account_id) ?? '—'}</td>
              )}
              {reserve && (
                <td className="category-txns__account">
                  {(t.category_id && categoryName.get(t.category_id)) || '—'}
                </td>
              )}
              <td
                className={`category-txns__amount tabular ${figureClass('flow', signTone(t.amount))}`}
              >
                {formatMoney(t.amount)}
              </td>
              {showRunning && (
                <td className="category-txns__running tabular">
                  {/* A pending row has no entry: it has not moved the
                  balance, and a zero here would say it had. */}
                  {formatMoneyOrDash(running[t.id])}
                </td>
              )}
              <td className="category-txns__open">
                <button
                  type="button"
                  className="category-txns__open-btn"
                  aria-label="Open in account register"
                  title="Open in account register"
                  onClick={(e) => {
                    e.stopPropagation()
                    openInRegister(t)
                  }}
                >
                  <ArrowUpRight size={14} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  return (
    <Modal onClose={onClose} historyKey="category-txns">
      <div className="category-txns" role="dialog" aria-modal aria-labelledby="category-txns-title">
        <div className="category-txns__header">
          <span id="category-txns-title" className="category-txns__title">
            {title}
            <span className="category-txns__subtitle">
              {reserve && month
                ? `What set money aside in ${formatMonth(month)}`
                : showAll
                  ? 'All transactions'
                  : month
                    ? formatMonth(month)
                    : 'Recent transactions'}
            </span>
          </span>
          <div className="category-txns__header-actions">
            {scope.kind === 'category' && (
              <select
                className="category-txns__account-filter"
                value={accountFilter}
                onChange={(e) => {
                  setAccountFilter(e.target.value)
                  setSelected(new Set())
                }}
                aria-label="Filter by account"
              >
                <option value="">All accounts</option>
                {openAccounts(accounts).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              className="category-txns__close"
              onClick={onClose}
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="category-txns__body">
          {isPending ? (
            <div className="category-txns__empty">Loading…</div>
          ) : transactions.length === 0 ? (
            <div className="category-txns__empty">
              {scope.kind === 'card-reserve'
                ? 'Nothing on this card was filed to an envelope this month.'
                : scope.kind === 'account'
                  ? 'No transactions on this account yet.'
                  : accountFilter
                    ? 'No transactions in this category for that account.'
                    : 'No transactions in this category yet.'}
            </div>
          ) : (
            <>
              {showRunning && (
                <p className="category-txns__running-note">
                  Balance runs down to what this account holds. On a card, Set aside is the envelope
                  beside it — not a total of these rows.
                </p>
              )}
              {renderTable(transactions)}
            </>
          )}
          {/* Under the list, inside the one scroller: the lines that take
            these rows to Set aside. Drawn once the rows are in, since the
            first line is their total. */}
          {scope.kind === 'card-reserve' && !isPending && data && (
            // The opened month's total only: Set aside is that month's figure,
            // and the earlier months below are context, not part of it.
            <CardReserveSummary
              budgetId={budgetId}
              accountId={scope.accountId}
              month={scope.month}
              listedNet={data.total_amount}
            />
          )}
          {earlierMonths.map((m, i) => {
            const q = earlier[i]
            const rows = q?.data?.transactions ?? []
            return (
              <section key={m} className="category-txns__month" aria-label={formatMonth(m)}>
                <div className="category-txns__month-head">
                  <h3 className="category-txns__month-title">{formatMonth(m)}</h3>
                  {q?.data && (
                    <span className="category-txns__count">
                      {q.data.total_count} transaction{q.data.total_count !== 1 ? 's' : ''} ·{' '}
                      <span className="tabular">{formatMoney(q.data.total_amount)}</span>
                    </span>
                  )}
                </div>
                {!q || q.isPending ? (
                  <div className="category-txns__empty">Loading…</div>
                ) : rows.length === 0 ? (
                  <div className="category-txns__empty">
                    Nothing on this card was filed to an envelope in {formatMonth(m)}.
                  </div>
                ) : (
                  renderTable(rows)
                )}
              </section>
            )
          })}
        </div>

        <div className="category-txns__footer">
          {picked.length > 0 ? (
            <>
              <span className="category-txns__count">{picked.length} selected</span>
              <span className="category-txns__selection-total tabular">
                {formatMoney(pickedTotal)}
              </span>
              <button
                type="button"
                className="category-txns__footer-btn"
                onClick={() => setSelected(new Set())}
              >
                Clear
              </button>
            </>
          ) : (
            <>
              {onAddTransaction && (
                <button
                  type="button"
                  className="category-txns__footer-btn"
                  onClick={onAddTransaction}
                >
                  <Plus size={13} />
                  Add transaction
                </button>
              )}
              <button
                type="button"
                className="category-txns__footer-btn"
                onClick={openInTransactions}
                title={
                  scope.kind === 'category'
                    ? 'Open the all-accounts register filtered to this category'
                    : 'Open the all-accounts register filtered to this account'
                }
              >
                <ArrowUpRight size={13} />
                Open in Transactions
              </button>
            </>
          )}
          <span className="category-txns__footer-spacer" />
          {reserve ? (
            nextEarlier && canStepBack ? (
              <button
                type="button"
                className="category-txns__footer-btn category-txns__footer-btn--primary"
                onClick={() => setMonthsBack((n) => n + 1)}
              >
                <ChevronLeft size={13} />
                Show {formatMonth(nextEarlier)} too
              </button>
            ) : (
              month &&
              monthsBack > 0 && (
                <button
                  type="button"
                  className="category-txns__footer-btn"
                  onClick={() => {
                    setMonthsBack(0)
                    setSelected(new Set())
                  }}
                >
                  Back to {formatMonth(month)} only
                </button>
              )
            )
          ) : budgetMonth ? (
            // The month is all here; older rows are what "all" adds, and the
            // month's count says nothing about how many of those there are.
            <button
              type="button"
              className="category-txns__footer-btn category-txns__footer-btn--primary"
              onClick={() => {
                setShowAll(true)
                setSelected(new Set())
              }}
            >
              Load all transactions
            </button>
          ) : totalCount > transactions.length ? (
            <button
              type="button"
              className="category-txns__footer-btn category-txns__footer-btn--primary"
              onClick={() => {
                setShowAll(true)
                setSelected(new Set())
              }}
            >
              View all {totalCount} transactions
            </button>
          ) : (
            totalCount > 0 && (
              <span className="category-txns__count">
                {totalCount} transaction{totalCount !== 1 ? 's' : ''}
              </span>
            )
          )}
        </div>
      </div>
    </Modal>
  )
}
