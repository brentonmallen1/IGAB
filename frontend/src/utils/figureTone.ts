import type { CategoryBalance } from '../types'

/**
 * How a budget figure is coloured — the one home for the rule.
 *
 * Fourteen places turned a sign into a colour class by hand before this
 * existed, and they had drifted: the preview dialogs drew a Ready to Assign of
 * zero green while the hero drew it muted, the multi-month sheet and the
 * inspector painted card-funded red as the alarm while the grid drew it calm,
 * and the inspector coloured Assigned green while the grid's Assigned column
 * is plain. Every budget figure now asks here, and carries a role so the
 * colour setting (`BudgetColorMode`) can quiet one kind without the other.
 */

/** The four readings a budget figure can have. Zero and on-card are muted in
 *  every colour mode: they are not hue signals. */
export type Tone = 'positive' | 'zero' | 'negative' | 'negative-on-card'

/**
 * What kind of figure it is, which is what the colour modes switch on:
 *
 * - `flow` — money that moved: Activity, an assignment's delta, a row's amount.
 * - `balance` — money that is there: Available, Ready to Assign, a card's
 *   Set aside.
 *
 * Two roles because there are exactly three modes — both painted, balances
 * only, neither.
 */
export type FigureRole = 'flow' | 'balance'

/** Sign alone: above zero, zero, below. */
export function signTone(n: number): 'positive' | 'zero' | 'negative' {
  return n > 0 ? 'positive' : n < 0 ? 'negative' : 'zero'
}

/**
 * The tone of a served Available, or of a sum of them.
 *
 * Red that was swiped on a card (`credit_overspent` covers all of it) is
 * still negative, but it never charges Ready to Assign and rides onto the
 * card at the month boundary — so it reads calmly, not as the alarm colour.
 * Both figures are the server's (domain/cards.py); this only names the
 * reading.
 *
 * A group's or a selection's total reads the same way over the summed
 * figures (`sumBalances`): it is calm when adding the card part back would
 * leave it at zero or above — when the card is the whole reason it is red.
 */
export function availableTone(
  balance: Pick<CategoryBalance, 'available' | 'credit_overspent'>
): Tone {
  const available = Number(balance.available ?? 0)
  const creditOverspent = Number(balance.credit_overspent ?? 0)
  if (available < 0) return creditOverspent >= -available ? 'negative-on-card' : 'negative'
  return available > 0 ? 'positive' : 'zero'
}

/**
 * Only the warning half of a tone: red, or the calm grey of red on a card.
 * For a figure that is a receipt rather than a reading — the quick-add toast,
 * the inspector's history — where a column of green would celebrate every
 * ordinary month.
 */
export function alarmOnly(tone: Tone): Tone | null {
  return tone === 'negative' || tone === 'negative-on-card' ? tone : null
}

/**
 * The classes a budget figure carries: `budget-figure`, its role, and its
 * tone (base.css, "Budget figures"). Null tone means plain in every mode.
 */
export function figureClass(role: FigureRole, tone: Tone | null): string {
  return tone ? `budget-figure budget-figure--${role} ${tone}` : ''
}

/**
 * Which budget figures are coloured, per device:
 *
 * - `full` — flows and balances (the default).
 * - `available` — balances only; Activity and the other flows are plain.
 * - `none` — nothing; an overspent envelope keeps its weight and its left
 *   edge, drawn in a neutral tone.
 *
 * Applied as `data-budget-colors` on <html> (appStore), read by base.css.
 */
export const BUDGET_COLOR_MODES = ['full', 'available', 'none'] as const
export type BudgetColorMode = (typeof BUDGET_COLOR_MODES)[number]

/** What each mode is called, and what it does. */
export const BUDGET_COLOR_MODE_COPY: Record<BudgetColorMode, { label: string; desc: string }> = {
  full: {
    label: 'Full colour',
    desc: 'Activity and Available are both coloured.',
  },
  available: {
    label: 'Available only',
    desc: 'Activity is plain. What is left in each envelope keeps its colour.',
  },
  none: {
    label: 'No colour',
    desc: 'Every figure is plain. An overspent envelope keeps its bold figure and its edge.',
  },
}

export function normalizeBudgetColorMode(value: unknown): BudgetColorMode {
  return BUDGET_COLOR_MODES.includes(value as BudgetColorMode) ? (value as BudgetColorMode) : 'full'
}
