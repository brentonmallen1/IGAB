/** Format a number as currency string (e.g. 1234.56 → "$1,234.56") */
export function formatMoney(
  amount: number,
  currencyCode = 'USD',
  locale = 'en-US'
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: currencyCode,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

/** Format amount without currency symbol */
export function formatAmount(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

/**
 * Parse a formatted money string back to a number.
 * Returns NaN for unparseable input — callers must guard with isNaN rather
 * than silently writing $0 into the ledger.
 */
export function parseMoney(value: string): number {
  const cleaned = value.replace(/[^0-9.-]/g, '')
  if (cleaned === '') return NaN
  return parseFloat(cleaned)
}

// ── Cents-integer arithmetic ──────────────────────────────────────────────────
// All client-side money math goes through integer cents: IEEE 754 makes
// 999.99 - 999.89 !== 0.10, so float compares on sums are never safe.
// The backend (Decimal end-to-end) stays authoritative; these helpers only
// keep client-side validation in agreement with it.

/** Convert a decimal amount (or amount string) to integer cents. NaN-safe. */
export function toCents(amount: number | string): number {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(n)) return NaN
  return Math.round(n * 100)
}

/** Convert integer cents back to a decimal amount. */
export function fromCents(cents: number): number {
  return cents / 100
}

/** Sum a list of amount strings (form inputs) exactly, in cents. */
export function sumToCents(amounts: Array<number | string>): number {
  return amounts.reduce<number>((sum, a) => {
    const c = toCents(a)
    return sum + (isNaN(c) ? 0 : c)
  }, 0)
}

export function isNegative(amount: number): boolean {
  return amount < 0
}

export function isPositive(amount: number): boolean {
  return amount > 0
}

/** Returns CSS class based on sign */
export function amountClass(amount: number): string {
  if (amount < 0) return 'amount-negative'
  if (amount > 0) return 'amount-positive'
  return 'amount-zero'
}
