/**
 * Stay put or transfer? Plain amortisation you can check by hand.
 *
 * Each month: interest accrues on the balance at that month's APR, then the
 * payment comes off. "Never pays off" is when a payment does not cover the
 * first month's interest. A transfer starts from the balance plus the fee and
 * runs at the promo APR for the promo months, then the ordinary APR.
 */

export interface TransferInputs {
  balance: number
  /** Annual percent on the current card. */
  currentApr: number
  /** What you will pay each month, on either card. */
  payment: number
  /** Percent of the balance charged once, at transfer. */
  feePercent: number
  promoMonths: number
  /** Annual percent during the promo, usually 0. */
  promoApr: number
  /** Annual percent after the promo, on the new card. */
  postPromoApr: number
}

export interface PayoffOutcome {
  /** null = never pays off at this payment. */
  months: number | null
  interest: number
  /** Balance left when the promo ends (transfer only). */
  balanceAtPromoEnd?: number
}

export interface TransferComparison {
  stay: PayoffOutcome
  transfer: PayoffOutcome & { fee: number }
  /** Positive = the transfer costs less overall (interest + fee). */
  saving: number
}

const MAX_MONTHS = 600

function simulate(
  start: number,
  payment: number,
  aprFor: (month: number) => number,
  promoMonths = 0
): PayoffOutcome {
  let balance = start
  let interest = 0
  let balanceAtPromoEnd: number | undefined
  for (let month = 0; month < MAX_MONTHS; month++) {
    if (promoMonths > 0 && month === promoMonths) balanceAtPromoEnd = round(balance)
    const accrued = (balance * aprFor(month)) / 1200
    if (payment <= accrued && aprFor(month) > 0) {
      return { months: null, interest: round(interest), balanceAtPromoEnd }
    }
    interest += accrued
    balance = balance + accrued - payment
    if (balance <= 0) {
      if (promoMonths > 0 && balanceAtPromoEnd === undefined) balanceAtPromoEnd = 0
      return { months: month + 1, interest: round(interest), balanceAtPromoEnd }
    }
  }
  return { months: null, interest: round(interest), balanceAtPromoEnd }
}

export function compareTransfer(i: TransferInputs): TransferComparison {
  const stay = simulate(i.balance, i.payment, () => i.currentApr)
  const fee = round((i.balance * i.feePercent) / 100)
  const transfer = simulate(
    i.balance + fee,
    i.payment,
    (month) => (month < i.promoMonths ? i.promoApr : i.postPromoApr),
    i.promoMonths
  )
  return {
    stay,
    transfer: { ...transfer, fee },
    saving: round(stay.interest - (transfer.interest + fee)),
  }
}

function round(n: number): number {
  return Math.round(n * 100) / 100
}
