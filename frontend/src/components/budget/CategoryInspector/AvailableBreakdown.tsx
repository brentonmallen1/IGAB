import { useFormatters } from '../../../hooks/useFormatters'
import type { CategoryBalance } from '../../../types'
import { sumBalances } from '../budgetTotals'
import { BalanceBreakdownRows } from './BalanceBreakdownRows'

interface Props {
  balances: CategoryBalance[]
  /** Same categories, previous month — enables the "vs last month" delta line */
  prevBalances?: CategoryBalance[]
}

export function AvailableBreakdown({ balances, prevBalances }: Props) {
  const { formatMoney } = useFormatters()
  const totals = sumBalances(balances)
  const { available: totalAvailable, assigned: totalAssigned, activity: totalActivity } = totals

  const deltas = prevBalances
    ? (() => {
        const prev = sumBalances(prevBalances)
        return {
          assigned: totalAssigned - prev.assigned,
          activity: totalActivity - prev.activity,
          available: totalAvailable - prev.available,
        }
      })()
    : null

  const fmtDelta = (d: number) => (d > 0 ? `+${formatMoney(d)}` : formatMoney(d))

  return (
    <div className="inspector-section">
      <div className="inspector-section__title">Available Balance</div>
      <div className="inspector-breakdown">
        <BalanceBreakdownRows
          totals={totals}
          labels={{
            leftOver: 'Cash Left Over From Last Month',
            assigned: 'Assigned This Month',
            activity: 'Spending',
          }}
        />
        {deltas && (
          <div className="inspector-breakdown__delta">
            <span className="inspector-breakdown__delta-label">vs last month</span>
            <span className="inspector-breakdown__delta-items tabular">
              {fmtDelta(deltas.assigned)} assigned · {fmtDelta(deltas.activity)} activity ·{' '}
              {fmtDelta(deltas.available)} available
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
