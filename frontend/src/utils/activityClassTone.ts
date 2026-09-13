/**
 * The tone a served activity class is drawn in — the one mapping from class
 * to colour role, read by the Event Timeline's dots and the Guide's class
 * chips. It lived in the timeline's own module until the Guide needed it too.
 */

/** Colour roles, not colours: each reader maps them to its own tokens. */
export type ActivityClassTone = 'income' | 'expense' | 'savings' | 'neutral'

const TONE_BY_CLASS: Record<string, ActivityClassTone> = {
  income: 'income',
  spending: 'expense',
  savings: 'savings',
  debt_principal: 'savings',
  investment_return: 'neutral',
  debt_interest: 'expense',
  transfer_internal: 'neutral',
}

/**
 * Tone by what a row means, not which way the amount points — so it takes no
 * amount. A transfer into savings is negative and is not an expense.
 *
 * A null class is a split whose legs disagree, and an unrecognised class is
 * one added server-side since; both get the neutral tone rather than a
 * sign-based guess. Falling back to the sign is the exact mislabelling the
 * activity taxonomy exists to end, and it is how an all-savings split came to
 * be drawn as a red expense.
 */
export function activityClassTone(activityClass: string | null): ActivityClassTone {
  return (activityClass !== null && TONE_BY_CLASS[activityClass]) || 'neutral'
}
