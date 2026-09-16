/**
 * What a surface that quotes the emergency fund says it counted.
 *
 * Pure composition of the served `EmergencyFund` — its parts are the server's
 * (`services/emergency_fund.py`); nothing here decides what counts or adds
 * anything up. The formatter is passed in so the privacy mask applies.
 */
import type { EmergencyFund } from '../../types'

/** Each counted part, in served order: envelopes, then accounts, then what is
 *  kept elsewhere. Empty when nothing is set up. */
export function countingParts(
  fund: EmergencyFund,
  formatMoney: (amount: number) => string
): string[] {
  if (!fund.set_up) return []
  const parts = [
    ...fund.categories.map((p) => `${p.name} envelope ${formatMoney(p.balance)}`),
    ...fund.accounts.map((p) => `${p.name} ${formatMoney(p.balance)}`),
  ]
  if (fund.external.declared) {
    // Declared without a figure is "I have this covered" — said, never $0.
    parts.push(
      fund.external.amount === null
        ? 'some kept elsewhere'
        : `kept elsewhere ${formatMoney(fund.external.amount)}`
    )
  }
  return parts
}

/** "Emergency Fund envelope $2,400.00 · Harborstone Reserve $6,000.00 · kept
 *  elsewhere $1,000.00", or null when nothing is set up. */
export function countingLine(
  fund: EmergencyFund,
  formatMoney: (amount: number) => string
): string | null {
  const parts = countingParts(fund, formatMoney)
  return parts.length ? parts.join(' · ') : null
}
