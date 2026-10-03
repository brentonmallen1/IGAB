import type { AutoAssignAction, CategoryBalance, CategoryHistory } from '../../../types'

export interface AutoAssignRow {
  action: AutoAssignAction
  label: string
  /** What the selected categories would hold assigned, summed. */
  value: number
}

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
  const history = (field: keyof CategoryHistory) =>
    (histories ?? []).reduce((sum, h) => sum + Number(h[field] ?? 0), 0)

  const selected = new Set(categoryIds)
  const targeted = (balances ?? []).filter(
    (b) => selected.has(b.category_id) && b.target_assigned !== null
  )

  return [
    ...(targeted.length > 0
      ? [
          {
            action: 'target_amount' as const,
            label: 'Target Amount',
            value: targeted.reduce((sum, b) => sum + Number(b.target_assigned), 0),
          },
        ]
      : []),
    {
      action: 'last_month_assigned',
      label: 'Assigned Last Month',
      value: history('last_month_assigned'),
    },
    { action: 'last_month_spent', label: 'Spent Last Month', value: history('last_month_spent') },
    { action: 'average_assigned', label: 'Average Assigned', value: history('average_assigned') },
    { action: 'average_spent', label: 'Average Spent', value: history('average_spent') },
  ]
}
