import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, Plus, X } from 'lucide-react'
import { useCategoryTransactions, usePayees } from '../../../api/transactions'
import { useAccounts } from '../../../api/accounts'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useHistoryDismissable } from '../../../hooks/useHistoryDismissable'
import type { Transaction } from '../../../types'
import './CategoryTransactionsModal.css'

const RECENT_LIMIT = 10
const ALL_LIMIT = 1000

interface Props {
  budgetId: string
  categoryId: string
  categoryName: string
  onClose: () => void
  /** Optional hand-off into the add-transaction flow for this category. */
  onAddTransaction?: () => void
}

/**
 * Budget-row drill-in: the most recent transactions for one category across
 * all accounts, narrowable to a single account. "View all" expands the list
 * in place so the user stays in the budget context; rows click through to the
 * account register, and "Open in Transactions" hands the same filters to the
 * all-accounts register page.
 */
export function CategoryTransactionsModal({
  budgetId,
  categoryId,
  categoryName,
  onClose,
  onAddTransaction,
}: Props) {
  const [accountFilter, setAccountFilter] = useState('')
  const [showAll, setShowAll] = useState(false)
  const navigate = useNavigate()
  const setTransactionSearch = useUIStore((s) => s.setTransactionSearch)
  const { formatMoney, formatDate } = useFormatters()
  const isMobile = useIsMobile()
  useHistoryDismissable(isMobile, onClose, 'category-txns')

  const { data, isPending } = useCategoryTransactions(
    budgetId,
    categoryId,
    showAll ? ALL_LIMIT : RECENT_LIMIT,
    accountFilter || null
  )
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: payees = [] } = usePayees(budgetId)

  const accountName = useMemo(() => new Map(accounts.map((a) => [a.id, a.name])), [accounts])
  const payeeName = useMemo(() => new Map(payees.map((p) => [p.id, p.name])), [payees])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const transactions = data?.transactions ?? []
  const totalCount = data?.total_count ?? 0

  function describePayee(t: Transaction): string {
    if (t.payee_id) return payeeName.get(t.payee_id) ?? '—'
    if (t.transfer_id) return 'Transfer'
    return t.import_description ?? '—'
  }

  function openInRegister(t: Transaction) {
    onClose()
    navigate(`/accounts/${t.account_id}?highlight=${t.id}`)
  }

  function openInTransactions() {
    // Land on the all-accounts register pre-filtered to this category (and
    // account, if narrowed here) via the shared search-token state
    const accountToken = accountFilter
      ? ` account:"${accountName.get(accountFilter) ?? ''}"`
      : ''
    setTransactionSearch(`category:"${categoryName}"${accountToken}`)
    onClose()
    navigate('/transactions')
  }

  return (
    <div
      className="category-txns-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="category-txns" role="dialog" aria-modal aria-labelledby="category-txns-title">
        <div className="category-txns__header">
          <span id="category-txns-title" className="category-txns__title">
            {categoryName}
            <span className="category-txns__subtitle">
              {showAll ? 'All transactions' : 'Recent transactions'}
            </span>
          </span>
          <div className="category-txns__header-actions">
            <select
              className="category-txns__account-filter"
              value={accountFilter}
              onChange={(e) => setAccountFilter(e.target.value)}
              aria-label="Filter by account"
            >
              <option value="">All accounts</option>
              {accounts.filter((a) => !a.is_closed).map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <button type="button" className="category-txns__close" onClick={onClose} aria-label="Close">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="category-txns__body">
          {isPending ? (
            <div className="category-txns__empty">Loading…</div>
          ) : transactions.length === 0 ? (
            <div className="category-txns__empty">
              {accountFilter
                ? 'No transactions in this category for that account.'
                : 'No transactions in this category yet.'}
            </div>
          ) : (
            <table className="category-txns__table">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Payee</th>
                  <th scope="col">Account</th>
                  <th scope="col" className="category-txns__amount-col">Amount</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => openInRegister(t)}
                    title="Open in account register"
                  >
                    <td className="category-txns__date">{formatDate(t.date)}</td>
                    <td className="category-txns__payee">
                      <span className="category-txns__payee-name">{describePayee(t)}</span>
                      {t.memo && <span className="category-txns__memo">{t.memo}</span>}
                    </td>
                    <td className="category-txns__account">{accountName.get(t.account_id) ?? '—'}</td>
                    <td
                      className={`category-txns__amount tabular ${Number(t.amount) < 0 ? 'negative' : 'positive'}`}
                    >
                      {formatMoney(Number(t.amount))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="category-txns__footer">
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
            title="Open the all-accounts register filtered to this category"
          >
            <ArrowUpRight size={13} />
            Open in Transactions
          </button>
          <span className="category-txns__footer-spacer" />
          {totalCount > transactions.length ? (
            <button
              type="button"
              className="category-txns__footer-btn category-txns__footer-btn--primary"
              onClick={() => setShowAll(true)}
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
    </div>
  )
}
