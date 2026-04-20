import { formatMoney } from '../../../utils/money'
import type { CategoryBalance } from '../../../types'

interface Props {
  balances: CategoryBalance[]
}

export function AvailableBreakdown({ balances }: Props) {
  const totalAvailable = balances.reduce((s, b) => s + Number(b.available), 0)
  const totalAssigned = balances.reduce((s, b) => s + Number(b.assigned), 0)
  const totalActivity = balances.reduce((s, b) => s + Number(b.activity), 0)
  const carriedOver = totalAvailable - totalAssigned - totalActivity

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
      </div>
    </div>
  )
}
