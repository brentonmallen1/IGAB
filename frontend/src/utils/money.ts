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

/** Parse a formatted money string back to a number */
export function parseMoney(value: string): number {
  const cleaned = value.replace(/[^0-9.-]/g, '')
  const parsed = parseFloat(cleaned)
  return isNaN(parsed) ? 0 : parsed
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
