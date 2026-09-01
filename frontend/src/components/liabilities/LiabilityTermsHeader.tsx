import { AlertTriangle, ArrowUpRight, Banknote, Pencil } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useLiabilities } from '../../api/liabilities'
import { useAssets } from '../../api/assets'
import { useFormatters } from '../../hooks/useFormatters'
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
  const { formatMoney, formatMonth } = useFormatters()
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
        {/* Cards and loans both: for a card this is the transfer that spends
            the set-aside; for a loan it is the same transfer plus an
            "extra to principal" field, so a curtailment is one decision at
            record time instead of a hand-typed register row. */}
        <button
          type="button"
          className="liability-terms__btn"
          onClick={() => openModal('card-payment', accountId)}
        >
          <Banknote size={12} />
          {isLoan ? 'Record a payment' : 'Make a payment'}
        </button>
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
