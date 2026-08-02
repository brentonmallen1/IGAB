import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { TransactionTable } from '../../components/transactions/TransactionTable/TransactionTable'
import { useAppStore } from '../../stores/appStore'
import './AllTransactionsPage.css'

/**
 * The all-accounts register: every transaction in the budget in one table,
 * with an account column identifying where each row lives. Same search,
 * sorting, inline editing, and bulk actions as a single account's register.
 */
export function AllTransactionsPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [searchParams, setSearchParams] = useSearchParams()
  const highlightId = searchParams.get('highlight')

  const clearHighlight = useCallback(() => {
    if (highlightId) {
      setSearchParams((prev) => {
        prev.delete('highlight')
        return prev
      }, { replace: true })
    }
  }, [highlightId, setSearchParams])

  if (!budgetId) {
    return <div className="all-txns-page__not-found">No budget selected.</div>
  }

  return (
    <div className="all-txns-page">
      <div className="all-txns-page__header">
        <div className="all-txns-page__name">All Transactions</div>
        <span className="all-txns-page__hint">
          Every account in this budget — filter with <code>account:</code>,{' '}
          <code>category:</code>, or <code>payee:</code>
        </span>
      </div>
      <div className="all-txns-page__body">
        <TransactionTable
          accountId={null}
          budgetId={budgetId}
          highlightId={highlightId}
          onInteraction={clearHighlight}
        />
      </div>
    </div>
  )
}
