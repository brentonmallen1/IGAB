/**
 * What the target badge and the compact/dense-row LED say — pure, so the
 * component file exports only the component (react-refresh) and the copy is
 * a one-line test.
 */

export type BadgeStatus = 'funded' | 'underfunded' | 'pending'

export const BADGE_LABELS: Record<BadgeStatus, string> = {
  funded: 'Funded',
  underfunded: 'Underfunded',
  pending: 'Pending',
}

/** A short ordinal for the day the target is checked on. */
export function ordinal(day: number): string {
  const rest = day % 100
  const suffix = rest >= 11 && rest <= 13 ? 'th' : (['th', 'st', 'nd', 'rd'][day % 10] ?? 'th')
  return `${day}${suffix}`
}

/** `needed` is the server's `needed_this_month`; `checkDay` is the day a
 *  pending target will be checked on (the target's own, else the budget's
 *  funding day). */
export function getTargetTooltip(
  status: BadgeStatus,
  needed: number | undefined,
  formatMoney: (amount: number) => string,
  checkDay?: number
): string {
  if (status === 'funded') return BADGE_LABELS.funded
  const amount = needed !== undefined && needed > 0 ? formatMoney(needed) : null
  if (status === 'pending') {
    const when = checkDay ? ` — checked after the ${ordinal(checkDay)}` : ''
    return amount ? `Pending: ${amount} still to assign${when}` : `${BADGE_LABELS.pending}${when}`
  }
  return amount ? `Need ${amount} this month` : BADGE_LABELS.underfunded
}
