import { useEffect, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useReportStore, type DrillDownContext } from '../../../stores/reportStore'
import { useBudgetTransactions, type BudgetTransactionParams } from '../../../api/transactions'
import { useAccounts } from '../../../api/accounts'
import { useCategories } from '../../../api/categories'
import { usePayees } from '../../../api/payees'
import { useFormatters } from '../../../hooks/useFormatters'
import { transactionDisplayPayee } from '../../../utils/transferDisplay'
import './DrillDownPanel.css'

const PAGE_SIZE = 200
// Backend caps limit at 1000; beyond that we tell the user to narrow the window
const MAX_ROWS = 1000

interface Props {
  budgetId: string
}

/** Inline transaction list under a report, driven by reportStore.drillDown.
 * The context arrives fully resolved (ids + window), so this component only
 * fetches, resolves display names, and renders. Keyed by context so per-drill
 * state (pagination) resets on every new drill. */
export function DrillDownPanel({ budgetId }: Props) {
  const { drillDown } = useReportStore()
  if (!drillDown) return null
  return (
    <DrillDownPanelInner
      key={JSON.stringify(drillDown)}
      budgetId={budgetId}
      drillDown={drillDown}
    />
  )
}

function DrillDownPanelInner({ budgetId, drillDown }: Props & { drillDown: DrillDownContext }) {
  const { formatMoney } = useFormatters()
  const { setDrillDown, filters } = useReportStore()
  const [limit, setLimit] = useState(PAGE_SIZE)
  const panelRef = useRef<HTMLDivElement>(null)

  const { data: accounts } = useAccounts(budgetId)
  const { data: categories } = useCategories(budgetId)
  const { data: payees } = usePayees(budgetId)

  useEffect(() => {
    panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [])

  const params: BudgetTransactionParams = useMemo(
    () => ({
      startDate: drillDown.startDate,
      endDate: drillDown.endDate,
      scope: drillDown.scope,
      direction: drillDown.direction,
      categoryIds: drillDown.categoryIds,
      payeeIds: drillDown.payeeIds,
      dayOfWeek: drillDown.dayOfWeek,
      activityClasses: drillDown.activityClasses,
      accountIds: filters.accountIds.length > 0 ? filters.accountIds : undefined,
      limit,
    }),
    [drillDown, filters.accountIds, limit]
  )

  const { data, isLoading, isError } = useBudgetTransactions(budgetId, params)

  const accountName = useMemo(
    () => new Map((accounts ?? []).map((a) => [a.id, a.name])),
    [accounts]
  )
  const categoryName = useMemo(
    () => new Map((categories ?? []).map((c) => [c.id, c.name])),
    [categories]
  )
  const payeeName = useMemo(() => new Map((payees ?? []).map((p) => [p.id, p.name])), [payees])

  const rows = data?.transactions ?? []
  const totalCount = data?.total_count ?? 0
  const totalAmount = Math.abs(Number(data?.total_amount ?? 0))
  const canLoadMore = rows.length < totalCount && limit < MAX_ROWS

  return (
    <div className="ddp surface" ref={panelRef}>
      <div className="ddp__header">
        <div className="ddp__heading">
          <h3 className="ddp__title">Transactions — {drillDown.label}</h3>
          <span className="ddp__window">
            {drillDown.startDate} – {drillDown.endDate}
          </span>
          {data && (
            <span className="ddp__summary">
              {totalCount} transaction{totalCount === 1 ? '' : 's'} · {formatMoney(totalAmount)}
            </span>
          )}
        </div>
        <button
          className="ddp__close"
          onClick={() => setDrillDown(null)}
          aria-label="Close transaction list"
          type="button"
        >
          <X size={16} />
        </button>
      </div>

      {isLoading && <div className="report-loading">Loading…</div>}
      {isError && <div className="ddp__error">Could not load transactions.</div>}
      {data && rows.length === 0 && (
        <div className="reports-empty">No transactions match this selection.</div>
      )}

      {rows.length > 0 && (
        <div className="ddp__scroll">
          <table className="ddp__table">
            <caption className="sr-only">Matching transactions</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Account</th>
                <th scope="col">Payee</th>
                <th scope="col">Category</th>
                <th scope="col">Memo</th>
                <th scope="col" className="ddp__num">
                  Amount
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => {
                const amount = t.amount
                return (
                  <tr key={t.id}>
                    <td className="ddp__date">{t.date}</td>
                    <td>{accountName.get(t.account_id) ?? ''}</td>
                    <td>
                      {t.payee_id || t.counterpart_account_id
                        ? transactionDisplayPayee(t, payeeName, accountName)
                        : ''}
                    </td>
                    <td>
                      {t.is_split
                        ? 'Split'
                        : t.category_id
                          ? (categoryName.get(t.category_id) ?? '')
                          : t.counterpart_account_id || t.transfer_id
                            ? 'Transfer'
                            : ''}
                    </td>
                    <td className="ddp__memo">{t.memo ?? ''}</td>
                    <td
                      className={`ddp__num ${amount < 0 ? 'ddp__amount--neg' : 'ddp__amount--pos'}`}
                    >
                      {formatMoney(amount)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {canLoadMore && (
        <button
          className="report-btn ddp__more"
          onClick={() => setLimit((l) => Math.min(l + PAGE_SIZE, MAX_ROWS))}
          type="button"
        >
          Load more ({rows.length} of {totalCount})
        </button>
      )}
      {!canLoadMore && rows.length < totalCount && (
        <div className="ddp__truncated">
          Showing first {rows.length} of {totalCount} — narrow the date range to see the rest.
        </div>
      )}
    </div>
  )
}
