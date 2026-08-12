import { useFormatters } from '../../../hooks/useFormatters'
import type { CategoryBalance } from '../../../types'

interface Props {
  balances: CategoryBalance[]
  /** Same categories, previous month — enables the "vs last month" delta line */
  prevBalances?: CategoryBalance[]
}

export function AvailableBreakdown({ balances, prevBalances }: Props) {
  const { formatMoney } = useFormatters()
  const totalAvailable = balances.reduce((s, b) => s + Number(b.available), 0)
  const totalAssigned = balances.reduce((s, b) => s + Number(b.assigned), 0)
  const totalActivity = balances.reduce((s, b) => s + Number(b.activity), 0)
  const carriedOver = totalAvailable - totalAssigned - totalActivity

  const deltas = prevBalances
    ? {
        assigned: totalAssigned - prevBalances.reduce((s, b) => s + Number(b.assigned), 0),
        activity: totalActivity - prevBalances.reduce((s, b) => s + Number(b.activity), 0),
        available: totalAvailable - prevBalances.reduce((s, b) => s + Number(b.available), 0),
      }
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
