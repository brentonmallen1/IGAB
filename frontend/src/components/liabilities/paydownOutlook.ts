import type { AmortizationResponse } from '../../api/liabilities'

/**
 * Which payoff the page should lead with: what you are actually paying, or
 * what the contract's minimum would do.
 *
 * The Liability page reported "Interest Remaining" and "Months Remaining"
 * from the contractual baseline, labelled *At minimum payment*, and nothing
 * else. For a household paying well above the minimum — a mortgage with a
 * separate curtailment row every month, say — both headline numbers described
 * a repayment nobody was making. The report was "show actual rather than an
 * assumed periodic thing from the minimum payment".
 *
 * So the observed pace leads when there is one, and the contractual figure
 * moves to the sub-line rather than disappearing: it is what the loan does if
 * you stop paying extra, which is a real thing to want to know. When there is
 * too little history to establish a pace, the minimum leads exactly as before.
 *
 * Pure, and takes the whole response rather than reading a query, so each of
 * these branches is a one-line test. Every figure in it is the server's — the
 * live schedule is computed there beside the baseline, from a median month
 * (`typical_recent_payment`), so the two can never be built differently.
 */

export type OutlookBasis = 'live' | 'minimum' | 'unknown'

export interface PaydownOutlook {
  basis: OutlookBasis
  /** Interest still to pay on the leading basis; null when it never clears. */
  interest: number | null
  /** Months still to pay on the leading basis; null when it never clears. */
  months: number | null
  /** Under the headline: what the other basis says, or why there is no number. */
  interestNote: string
  monthsNote: string
  /** The pace the live figures assume, for the caption. */
  typicalPayment: number | null
}

const MINIMUM_LABEL = 'At the minimum payment'
const NO_TERMS = 'Needs APR and minimum payment'

/**
 * `formatMoney` is passed in rather than imported so this stays pure and the
 * caller's currency/format settings are the ones used.
 */
export function paydownOutlook(
  amortization: AmortizationResponse | undefined,
  formatMoney: (n: number) => string
): PaydownOutlook {
  const unknown: PaydownOutlook = {
    basis: 'unknown',
    interest: null,
    months: null,
    interestNote: NO_TERMS,
    monthsNote: NO_TERMS,
    typicalPayment: null,
  }
  if (!amortization) return unknown
  if (!amortization.terms_complete) return unknown

  const baselineNever = amortization.baseline_never_pays_off
  const baselineInterest = baselineNever ? null : (amortization.baseline_total_interest ?? null)
  const baselineMonths = baselineNever ? null : amortization.baseline_schedule.length

  // A live projection exists only with two months of payments behind it, and
  // carries totals only when that pace actually clears the debt.
  const hasLive = amortization.live_months !== null && amortization.live_total_interest !== null
  if (!hasLive) {
    return {
      basis: 'minimum',
      interest: baselineInterest,
      months: baselineMonths,
      interestNote: baselineNever ? "The minimum doesn't cover interest" : MINIMUM_LABEL,
      monthsNote: baselineNever ? "The minimum doesn't cover interest" : MINIMUM_LABEL,
      typicalPayment: amortization.live_typical_payment,
    }
  }

  const pace = amortization.live_typical_payment
  const paceLabel = pace === null ? 'At your recent pace' : `At about ${formatMoney(pace)}/mo`
  // What the loan does if the extra stops. Said, not hidden — it is the
  // number the contract promises and the reason the extra is worth paying.
  const interestNote = baselineNever
    ? `${paceLabel} · the minimum alone wouldn't cover interest`
    : baselineInterest !== null
      ? `${paceLabel} · ${formatMoney(baselineInterest)} at the minimum`
      : paceLabel
  const monthsNote = baselineNever
    ? `${paceLabel} · the minimum alone wouldn't cover interest`
    : baselineMonths !== null
      ? `${paceLabel} · ${baselineMonths} at the minimum`
      : paceLabel

  return {
    basis: 'live',
    interest: amortization.live_total_interest,
    months: amortization.live_months,
    interestNote,
    monthsNote,
    typicalPayment: pace,
  }
}
