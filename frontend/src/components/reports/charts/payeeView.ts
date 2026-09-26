/**
 * How Payee Analysis states what the server decided. The rule — how many of
 * the window's months make a payee recurring — is the server's
 * (`domain.spending.recurring_months`), served as `recurring_min_months`;
 * this only says it in words, once, for the subtitle, the key and the
 * button.
 */

/** The key's and subtitle's statement of the recurring rule. */
export function recurringRule(minMonths: number | null): string {
  return minMonths === null
    ? 'Recurring needs a range of 3+ months'
    : `Recurring = seen in ${minMonths}+ months of the range`
}

/** A payee row's second line: whether it recurs, else how many purchases. */
export function payeeSubName(p: { is_recurring: boolean; count: number }): string {
  if (p.is_recurring) return 'Recurring'
  return `${p.count} purchase${p.count === 1 ? '' : 's'}`
}
