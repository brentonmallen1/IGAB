import type { AutoAssignAction, Category, CategoryBalance, CategoryHistory } from '../../../types'

export interface AutoAssignRow {
  action: AutoAssignAction
  label: string
  /** What the selected categories would hold assigned, summed. */
  value: number
}

type HistoryAction = Exclude<AutoAssignAction, 'reset' | 'target_amount'>

/**
 * The envelopes the month summary's buttons act on: every listed category
 * money may enter, by the served `is_fundable` (category_filters.IS_FUNDABLE).
 *
 * It sent every listed category, Income included, and the server refuses a
 * press that names an income category — so "Assigned Last Month" on the
 * month summary failed outright on any budget with an Income group. The
 * listing also carries categories of an archived group; those cannot be
 * funded either. The dropdown's strategies act on this same set
 * (`AssignService._gather`), so the two surfaces now agree on "all".
 */
export function autoAssignCategoryIds(categories: readonly Category[]): string[] {
  return categories.filter((c) => c.is_fundable).map((c) => c.id)
}

/**
 * What each selected envelope will hold assigned after `action` — the
 * figures the server sets, read from what it served: `target_assigned`
 * (TargetService.target_assigned) for Target Amount, the batch history for
 * the history buttons, zero for Reset. Envelopes the action leaves alone
 * (no target) are absent. Null while the history the figures come from has
 * not loaded: an unknown figure is not a zero.
 *
 * The button's own figure is the sum of these, and the optimistic update
 * draws exactly these, so what the button says, what the grid shows at once
 * and what the server writes are one set of numbers.
 */
export function autoAssignAmounts(
  action: AutoAssignAction,
  categoryIds: readonly string[],
  histories: readonly CategoryHistory[] | undefined,
  balances: readonly CategoryBalance[] | undefined
): Map<string, number> | null {
  const selected = new Set(categoryIds)
  if (action === 'reset') return new Map(categoryIds.map((id) => [id, 0]))
  if (action === 'target_amount') {
    return new Map(
      (balances ?? [])
        .filter((b) => selected.has(b.category_id) && b.target_assigned !== null)
        .map((b) => [b.category_id, Number(b.target_assigned)])
    )
  }
  if (!histories) return null
  const field: HistoryAction = action
  return new Map(
    histories
      .filter((h) => selected.has(h.category_id))
      .map((h) => [h.category_id, Number(h[field] ?? 0)])
  )
}

const total = (amounts: Map<string, number> | null) =>
  [...(amounts?.values() ?? [])].reduce((sum, v) => sum + v, 0)

/**
 * The inspector's Auto-Assign rows, for one category or many. Both the single
 * category's section and the month summary drew this list, each with its own
 * copy of the labels and the summing — so a new action (Target Amount) would
 * have had to be added twice.
 *
 * Target Amount appears only when a selected category has a target, and its
 * figure is the served `target_assigned` (TargetService.target_assigned —
 * the rule the POST runs), never recomputed here. Categories without a
 * target are left alone by it, so they add nothing to its figure.
 */
export function autoAssignRows(
  categoryIds: readonly string[],
  histories: readonly CategoryHistory[] | undefined,
  balances: readonly CategoryBalance[] | undefined
): AutoAssignRow[] {
  const value = (action: AutoAssignAction) =>
    total(autoAssignAmounts(action, categoryIds, histories, balances))
  const targeted = autoAssignAmounts('target_amount', categoryIds, histories, balances)

  return [
    ...(targeted && targeted.size > 0
      ? [{ action: 'target_amount' as const, label: 'Target Amount', value: total(targeted) }]
      : []),
    {
      action: 'last_month_assigned',
      label: 'Assigned Last Month',
      value: value('last_month_assigned'),
    },
    { action: 'last_month_spent', label: 'Spent Last Month', value: value('last_month_spent') },
    { action: 'average_assigned', label: 'Average Assigned', value: value('average_assigned') },
    { action: 'average_spent', label: 'Average Spent', value: value('average_spent') },
  ]
}
