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
  const { formatMonth, formatMoney } = useFormatters()

  if (Number(liability.current_balance) === 0) {
    return (
      <div className="payoff-pill payoff-pill--paid">
        <CheckCircle2 size={18} />
        <div className="payoff-pill__main">Paid off</div>
      </div>
    )
  }

  // Missing terms is a different absence from missing history, and the fix
  // differs too: enter an APR and a minimum, rather than wait for payments.
  // Every branch below reads a projection that does not exist yet.
  if (!liability.terms_complete) {
    const paying =
      liability.average_recent_payment !== null
        ? formatMoney(Number(liability.average_recent_payment))
        : null
    return (
      <div className="payoff-pill">
        <div>
          <div className="payoff-pill__main">No payoff estimate yet</div>
          <div className="payoff-pill__sub">
            {paying
              ? `You're paying about ${paying}/mo — add the APR and minimum payment for a payoff date`
              : 'Add the APR and minimum payment for a payoff date'}
          </div>
        </div>
      </div>
    )
  }

  const liveNever = liability.has_live_projection && liability.live_never_pays_off
  const baselineNever = liability.baseline_never_pays_off
  const interestNow = formatMoney(Number(liability.monthly_interest_now))
  const minimum = formatMoney(Number(liability.minimum_payment))

  // The warning must say WHICH payments fall short — "won't pay this off"
  // alone reads as "won't pay it off early".
  if (liveNever) {
    const avg =
      liability.average_recent_payment !== null
        ? formatMoney(Number(liability.average_recent_payment))
        : null
    return (
      <div className="payoff-pill payoff-pill--warning">
        <AlertTriangle size={18} />
        <div>
          <div className="payoff-pill__main">Your recent payments won't pay this off</div>
          <div className="payoff-pill__sub">
            {avg
              ? `Recent payments average ${avg}/mo — below this month's ~${interestNow} interest`
              : `Recent payments fall below this month's ~${interestNow} interest`}
            {!baselineNever && liability.baseline_payoff_date
              ? ` · at the ${minimum} minimum: ${formatMonth(liability.baseline_payoff_date)}`
              : ''}
          </div>
        </div>
      </div>
    )
  }

  if (baselineNever && !liability.has_live_projection) {
    return (
      <div className="payoff-pill payoff-pill--warning">
        <AlertTriangle size={18} />
        <div>
          <div className="payoff-pill__main">Won't pay off at the minimum payment</div>
          <div className="payoff-pill__sub">
            The {minimum} minimum doesn't cover this month's ~{interestNow} interest — your
            actual payments decide the real date
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
            {baselineNever
              ? `The ${minimum} minimum alone wouldn't cover interest — this date reflects what you actually pay`
              : differs && liability.baseline_payoff_date
                ? `At the ${minimum} minimum: ${formatMonth(liability.baseline_payoff_date)}`
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
