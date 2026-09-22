import { AlertTriangle, ArrowUpRight, Pencil } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useLiabilities } from '../../api/liabilities'
import { useAssets } from '../../api/assets'
import { useFormatters } from '../../hooks/useFormatters'
import { today } from '../../utils/dates'
import { describeDueRule, dueSoonNotice, nextDueDate } from '../../utils/paymentDue'
import { useUIStore } from '../../stores/uiStore'
import './LiabilityTermsHeader.css'
import { describeMinimumRule } from './minimumPaymentCopy'

interface Props {
  budgetId: string
  accountId: string
  /** Loans lean on the terms harder than cards do — a payoff date is the whole
   *  point of the page — so they get the stronger empty state. */
  isLoan: boolean
}

const NOT_SET = 'Not set'

/**
 * APR, minimum payment and payoff for a liability-classified account.
 *
 * Discoverability through presence rather than a banner: every such account
 * now carries a Liability row, so the page can simply have a place for the
 * numbers. Empty fields in a header that clearly wants them read as "fill this
 * in" without asking twice — which is why there is no prompt here, only a
 * header whose values happen to be blank.
 */
export function LiabilityTermsHeader({ budgetId, accountId, isLoan }: Props) {
  // formatDayMonth, not formatDate: the next due date is weeks away at
  // most, so the year is noise in a header this dense.
  const { formatMoney, formatMonth, formatDayMonth } = useFormatters()
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const { data: assets = [] } = useAssets(budgetId)
  const openModal = useUIStore((s) => s.openModal)

  const liability = liabilities.find((l) => l.linked_account_id === accountId)
  // Defensive: after the companion backfill every liability account has one,
  // but the header must not be what breaks if that is ever untrue.
  if (!liability) return null

  const termsSet = liability.terms_complete
  const payoff = liability.has_live_projection
    ? liability.live_payoff_date
    : liability.baseline_payoff_date
  const neverPays = liability.has_live_projection
    ? liability.live_never_pays_off
    : liability.baseline_never_pays_off

  const minimumRule = describeMinimumRule(liability, formatMoney)
  const securedAsset = assets.find((a) => a.id === liability.linked_asset_id) ?? null

  // The next date the bill falls due, and the rule that produced it. The two
  // are different facts — "Oct 4" and "every 31 days" — and the header shows
  // both, because a card on a cycle has a date that will not be that date
  // next month. Computed here rather than served: this is the side that knows
  // what day it is (utils/paymentDue.ts).
  const billDue = nextDueDate(liability, today())
  const billRule = describeDueRule(liability)
  // The indicator. `current_balance` is owed-POSITIVE, which is the sign
  // dueSoonNotice documents; the budget strip holds the same number the other
  // way round and converts at its own call site.
  const dueSoon = dueSoonNotice(liability, { today: today(), owed: liability.current_balance })

  return (
    <div className={`liability-terms ${termsSet ? '' : 'liability-terms--empty'}`}>
      <div className="liability-terms__items">
        <div className="liability-terms__item">
          <span className="liability-terms__value">
            {liability.interest_rate === null ? NOT_SET : `${liability.interest_rate}%`}
          </span>
          <span className="liability-terms__label">APR</span>
        </div>
        <div className="liability-terms__item">
          <span className="liability-terms__value">
            {/* The computed figure, not the stored one: for a percentage rule
                they are different numbers, and the one on screen has to be
                the one the projections used. Served, because the server owns
                the balance and the interest. */}
            {liability.minimum_payment_due_now === null
              ? NOT_SET
              : formatMoney(liability.minimum_payment_due_now)}
          </span>
          <span className="liability-terms__label">Minimum payment</span>
          {minimumRule && <span className="liability-terms__sub">{minimumRule}</span>}
        </div>
        <div className="liability-terms__item">
          <span className="liability-terms__value">
            {!termsSet ? NOT_SET : neverPays ? '—' : payoff ? formatMonth(payoff) : '—'}
          </span>
          <span className="liability-terms__label">
            {neverPays && termsSet ? (
              <>
                <AlertTriangle size={10} />
                Payments don&apos;t cover interest
              </>
            ) : (
              'Paid off'
            )}
          </span>
        </div>
        {/* Loans only: what the debt is secured against. An empty field in a
            header that clearly wants it reads as "fill this in" without a
            banner — the header's own documented philosophy. The value is
            stated on the ASSET, dated; there is nothing to type here. */}
        {isLoan && (
          <div className="liability-terms__item">
            <span className="liability-terms__value">
              {securedAsset
                ? securedAsset.current_value === null
                  ? NOT_SET
                  : formatMoney(securedAsset.current_value)
                : NOT_SET}
            </span>
            <span className="liability-terms__label">
              {securedAsset ? `Value of ${securedAsset.name}` : 'Asset value'}
            </span>
            {securedAsset && (
              <Link className="liability-terms__sub" to={`/assets/${securedAsset.id}`}>
                Update on its page
              </Link>
            )}
          </div>
        )}
        {/* Cards only, and only once set: the bill's date is a reminder, not a
            term the projections need, so an empty slot has nothing to ask.
            The DATE leads and the rule explains it — on a fixed-length cycle
            the date is the only one of the two a person can act on, and the
            rule is the only one of the two that stays true next month.

            Coloured only when the bill is close AND the card still owes
            something, which is the one moment this field is news. */}
        {!isLoan && billDue !== null && (
          <div className="liability-terms__item">
            <span
              className={`liability-terms__value ${
                dueSoon ? 'liability-terms__value--warning' : ''
              }`}
            >
              {formatDayMonth(billDue)}
            </span>
            <span className="liability-terms__label">
              {dueSoon ? `Bill due ${dueSoon.phrase}` : 'Bill due'}
            </span>
            {billRule && <span className="liability-terms__sub">{billRule}</span>}
          </div>
        )}
        {liability.credit_limit != null && liability.utilization != null && (
          <div className="liability-terms__item">
            <span
              className={`liability-terms__value ${
                liability.utilization >= 50
                  ? 'liability-terms__value--negative'
                  : liability.utilization >= 30
                    ? 'liability-terms__value--warning'
                    : ''
              }`}
            >
              {liability.utilization}%
            </span>
            <span className="liability-terms__label">
              of {formatMoney(liability.credit_limit)} limit
            </span>
          </div>
        )}
        {liability.promo_end_date && (
          <div className="liability-terms__item">
            <span className="liability-terms__value">{formatMonth(liability.promo_end_date)}</span>
            <span className="liability-terms__label">
              {liability.promo_deferred_interest ? 'Promo ends (deferred)' : 'Promo ends'}
            </span>
          </div>
        )}
      </div>

      <div className="liability-terms__actions">
        {/* The payment action lives in the register toolbar (`RegisterToolbar`),
            beside Add Transaction — this strip is the terms, not the doing. */}
        {!termsSet && (
          <span className="liability-terms__hint">
            {isLoan
              ? 'Add the APR and minimum payment for a payoff date, schedule and interest total.'
              : 'Add the APR and minimum payment to see what this card costs to carry.'}
          </span>
        )}
        <button
          type="button"
          className="liability-terms__btn"
          onClick={() => openModal('liability', liability.id)}
        >
          <Pencil size={12} />
          {termsSet ? 'Edit terms' : 'Add terms'}
        </button>
        {termsSet && (
          <Link className="liability-terms__link" to={`/liabilities/${liability.id}`}>
            Payoff detail
            <ArrowUpRight size={12} />
          </Link>
        )}
      </div>
    </div>
  )
}
