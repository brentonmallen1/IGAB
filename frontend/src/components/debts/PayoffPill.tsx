import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { Debt } from '../../api/debts'
import './PayoffPill.css'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function formatMonthYear(isoDate: string): string {
  const [year, month] = isoDate.split('-')
  return `${MONTHS[Number(month) - 1]} ${year}`
}

interface Props {
  debt: Debt
}

/**
 * The centerpiece of the debt page: when is this actually paid off?
 *
 * Four honest states — paid off; live estimate (with the contractual date
 * as secondary when they differ); contractual-only when payment history is
 * too thin for a live estimate; and a warning when current payments can
 * never retire the debt. A live number is never fabricated.
 */
export function PayoffPill({ debt }: Props) {
  if (Number(debt.current_balance) === 0) {
    return (
      <div className="payoff-pill payoff-pill--paid">
        <CheckCircle2 size={18} />
        <div className="payoff-pill__main">Paid off</div>
      </div>
    )
  }

  const liveNever = debt.has_live_projection && debt.live_never_pays_off
  const baselineNever = debt.baseline_never_pays_off
  if (liveNever || (baselineNever && !debt.has_live_projection)) {
    return (
      <div className="payoff-pill payoff-pill--warning">
        <AlertTriangle size={18} />
        <div>
          <div className="payoff-pill__main">Current payments won't pay this off</div>
          <div className="payoff-pill__sub">
            {liveNever && !baselineNever && debt.baseline_payoff_date
              ? `At the contractual payment: ${formatMonthYear(debt.baseline_payoff_date)}`
              : 'Interest outpaces the payment — increase your payment'}
          </div>
        </div>
      </div>
    )
  }

  if (debt.has_live_projection && debt.live_payoff_date) {
    const differs =
      debt.baseline_payoff_date !== null &&
      debt.baseline_payoff_date.slice(0, 7) !== debt.live_payoff_date.slice(0, 7)
    return (
      <div className="payoff-pill">
        <div>
          <div className="payoff-pill__main">
            Paid off around <strong>{formatMonthYear(debt.live_payoff_date)}</strong>
          </div>
          <div className="payoff-pill__sub">
            {differs && debt.baseline_payoff_date
              ? `Contractual: ${formatMonthYear(debt.baseline_payoff_date)}`
              : 'Based on your recent payments'}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="payoff-pill">
      <div>
        <div className="payoff-pill__main">
          {debt.baseline_payoff_date ? (
            <>
              Paid off by <strong>{formatMonthYear(debt.baseline_payoff_date)}</strong>
            </>
          ) : (
            'Payoff date unknown'
          )}
        </div>
        <div className="payoff-pill__sub">Add payment history for a live estimate</div>
      </div>
    </div>
  )
}
