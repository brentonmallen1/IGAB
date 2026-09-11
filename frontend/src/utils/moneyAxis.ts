/**
 * The money axis of every chart, sized for the screen it is on.
 *
 * Fourteen charts declared `<YAxis width={90}>` (or 80, or 85) with a
 * full-precision money formatter. On a 390pt phone a report card's plot is
 * ~290px wide, and a 90px axis of "$12,345.67" ticks took a third of it —
 * a chart you could not read beside labels you did not need. Phones get a
 * compact tick ("$12.3k") and the width it actually needs.
 */

export const MONEY_AXIS_WIDTH = {
  /** Room for "$12,345.67" at 11px. */
  desktop: 90,
  /** Room for "-$12.3k" at 11px. */
  phone: 52,
} as const

/**
 * "$1.2k", "$12k", "$1.5M", "$800", "-$1.2k". Rounded to what an axis tick
 * can say: one decimal under 10 units, none above. Never used for a figure
 * a person acts on — those keep every cent — only for the grid beside it.
 */
export function compactMoney(amount: number, symbol: string): string {
  const sign = amount < 0 ? '-' : ''
  const abs = Math.abs(amount)
  const unit = (n: number, suffix: string) => {
    const rounded = n < 10 ? Math.round(n * 10) / 10 : Math.round(n)
    return `${sign}${symbol}${rounded}${suffix}`
  }
  if (abs >= 1_000_000_000) return unit(abs / 1_000_000_000, 'B')
  if (abs >= 1_000_000) return unit(abs / 1_000_000, 'M')
  if (abs >= 1_000) return unit(abs / 1_000, 'k')
  return `${sign}${symbol}${Math.round(abs)}`
}
