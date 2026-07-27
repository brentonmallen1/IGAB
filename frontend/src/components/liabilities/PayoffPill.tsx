import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { Liability } from '../../api/liabilities'
import { useFormatters } from '../../hooks/useFormatters'
import './PayoffPill.css'

interface Props {
  liability: Liability
}

/**
 * The centerpiece of the liability page: when is this actually paid off?
 *
 * Four honest states — paid off; live estimate (with the contractual date
 * as secondary when they differ); contractual-only when payment history is
 * too thin for a live estimate; and a warning when current payments can
 * never retire the liability. A live number is never fabricated.
 */
export function PayoffPill({ liability }: Props) {
  const { formatMonth } = useFormatters()

  if (Number(liability.current_balance) === 0) {
    return (
      <div className="payoff-pill payoff-pill--paid">
        <CheckCircle2 size={18} />
        <div className="payoff-pill__main">Paid off</div>
      </div>
    )
  }

  const liveNever = liability.has_live_projection && liability.live_never_pays_off
  const baselineNever = liability.baseline_never_pays_off
  if (liveNever || (baselineNever && !liability.has_live_projection)) {
    return (
      <div className="payoff-pill payoff-pill--warning">
        <AlertTriangle size={18} />
        <div>
          <div className="payoff-pill__main">Current payments won't pay this off</div>
          <div className="payoff-pill__sub">
            {liveNever && !baselineNever && liability.baseline_payoff_date
              ? `At the contractual payment: ${formatMonth(liability.baseline_payoff_date)}`
              : 'Interest outpaces the payment — increase your payment'}
          </div>
        </div>
      </div>
    )
  }

  if (liability.has_live_projection && liability.live_payoff_date) {
    const differs =
      liability.baseline_payoff_date !== null &&
      liability.baseline_payoff_date.slice(0, 7) !== liability.live_payoff_date.slice(0, 7)
    return (
      <div className="payoff-pill">
        <div>
          <div className="payoff-pill__main">
            Paid off around <strong>{formatMonth(liability.live_payoff_date)}</strong>
          </div>
          <div className="payoff-pill__sub">
            {differs && liability.baseline_payoff_date
              ? `Contractual: ${formatMonth(liability.baseline_payoff_date)}`
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
          {liability.baseline_payoff_date ? (
            <>
              Paid off by <strong>{formatMonth(liability.baseline_payoff_date)}</strong>
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
