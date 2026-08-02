import type { NumberFormat } from '../types'

const SEPARATORS: Record<NumberFormat, [string, string]> = {
  comma_dot: [',', '.'],
  dot_comma: ['.', ','],
  space_comma: [' ', ','],
}

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  CAD: 'CA$',
  AUD: 'A$',
  CHF: 'CHF ',
  SEK: 'kr ',
  NOK: 'kr ',
  DKK: 'kr ',
  PLN: 'zł',
  CZK: 'Kč',
  INR: '₹',
  CNY: '¥',
  KRW: '₩',
  BRL: 'R$',
  MXN: 'MX$',
}

export function getCurrencySymbol(code: string): string {
  return CURRENCY_SYMBOLS[code] ?? `${code} `
}

function formatNumberWithSeparators(
  absAmount: number,
  numberFormat: NumberFormat
): string {
  const [thousands, decimal] = SEPARATORS[numberFormat]
  const [intPart, decPart] = absAmount.toFixed(2).split('.')
  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, thousands)
  return `${formattedInt}${decimal}${decPart}`
}

/** Format a number as currency string with configurable format */
export function formatMoneyWithOptions(
  amount: number,
  currencyCode: string,
  numberFormat: NumberFormat
): string {
  const sign = amount < 0 ? '-' : ''
  const symbol = getCurrencySymbol(currencyCode)
  const formatted = formatNumberWithSeparators(Math.abs(amount), numberFormat)
  return `${sign}${symbol}${formatted}`
}

/** Format amount without currency symbol, with configurable format */
export function formatAmountWithOptions(
  amount: number,
  numberFormat: NumberFormat
): string {
  const sign = amount < 0 ? '-' : ''
  const formatted = formatNumberWithSeparators(Math.abs(amount), numberFormat)
  return `${sign}${formatted}`
}

/** Format a number as currency string (e.g. 1234.56 → "$1,234.56") - legacy API */
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

/** Format amount without currency symbol - legacy API */
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

/**
 * Parse a user-typed amount from a free-text/decimal-keyboard input into a
 * non-negative number. Handles both separator conventions:
 * - "12,34" (decimal comma, 1–2 digits after) → 12.34
 * - "1,234" / "1,234.56" (comma grouping) → 1234 / 1234.56
 * Currency symbols and spaces are ignored. Returns NaN for unparseable input
 * and for negative input — outflow/inflow fields carry sign structurally.
 */
export function parseAmountInput(value: string): number {
  const trimmed = value.trim()
  if (trimmed === '') return NaN
  if (trimmed.includes('-')) return NaN
  let normalized: string
  const commas = (trimmed.match(/,/g) ?? []).length
  if (commas === 0) {
    normalized = trimmed
  } else if (trimmed.includes('.')) {
    // Both present: commas are grouping ("1,234.56")
    normalized = trimmed.replace(/,/g, '')
  } else if (commas === 1 && /,\d{1,2}$/.test(trimmed)) {
    // Single comma with 1–2 trailing digits: decimal comma ("12,34")
    normalized = trimmed.replace(',', '.')
  } else {
    // Comma grouping without decimals ("1,234" / "1,234,567")
    normalized = trimmed.replace(/,/g, '')
  }
  const cleaned = normalized.replace(/[^0-9.]/g, '')
  if (cleaned === '' || cleaned === '.' || (cleaned.match(/\./g) ?? []).length > 1) return NaN
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
