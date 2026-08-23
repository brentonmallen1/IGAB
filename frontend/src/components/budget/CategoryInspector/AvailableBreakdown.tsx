import { useFormatters } from '../../../hooks/useFormatters'
import type { CategoryBalance } from '../../../types'
import { sumBalances } from '../budgetTotals'

interface Props {
  balances: CategoryBalance[]
  /** Same categories, previous month — enables the "vs last month" delta line */
  prevBalances?: CategoryBalance[]
}

export function AvailableBreakdown({ balances, prevBalances }: Props) {
  const { formatMoney } = useFormatters()
  const {
    available: totalAvailable,
    assigned: totalAssigned,
    activity: totalActivity,
    carriedOver,
  } = sumBalances(balances)

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
        <div className="inspector-breakdown__row">
          <span>Cash Left Over From Last Month</span>
          <span className="tabular">{formatMoney(carriedOver)}</span>
        </div>
        <div className="inspector-breakdown__row">
          <span>Assigned This Month</span>
          <span className={`tabular ${totalAssigned > 0 ? 'positive' : ''}`}>
            {totalAssigned > 0 ? '+' : ''}{formatMoney(totalAssigned)}
          </span>
        </div>
        <div className="inspector-breakdown__row">
          <span>Spending</span>
          <span className={`tabular ${totalActivity < 0 ? 'negative' : ''}`}>
            {formatMoney(totalActivity)}
          </span>
        </div>
        <div className="inspector-breakdown__total">
          <span>Available</span>
          <span className={`tabular ${totalAvailable < 0 ? 'negative' : totalAvailable > 0 ? 'positive' : 'zero'}`}>
            {formatMoney(totalAvailable)}
          </span>
        </div>
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
