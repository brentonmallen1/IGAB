import type { AssignStrategy } from '../../../types'

/** Labels + descriptions shared by the dropdown rows and the preview modal. */
export const STRATEGY_META: Record<AssignStrategy, { label: string; description: string }> = {
  underfunded: {
    label: 'Underfunded Targets',
    description:
      'Fund each category up to its target, distributed proportionally within Ready to Assign.',
  },
  target_amount: {
    label: 'Target Amounts',
    description:
      "Set each targeted category's assigned amount to what its target asks this month — down as well as up, though never below what it has already spent. A savings balance is topped up, never lowered.",
  },
  last_month_assigned: {
    label: 'Assigned Last Month',
    description: "Set each category's assigned amount to what it was assigned last month.",
  },
  last_month_spent: {
    label: 'Spent Last Month',
    description: "Set each category's assigned amount to what it spent last month.",
  },
  average_assigned: {
    label: 'Average Assigned',
    description: "Set each category's assigned amount to its six-month average assigned.",
  },
  average_spent: {
    label: 'Average Spent',
    description: "Set each category's assigned amount to its six-month average spent.",
  },
  reduce_overfunded: {
    label: 'Reduce Overfunding',
    description:
      'Pull categories assigned beyond their target back to the target. The excess returns to Ready to Assign.',
  },
  reset_available: {
    label: 'Reset Available Amounts',
    description:
      "Return each category's positive Available balance to Ready to Assign. Overspent categories are left alone.",
  },
  reset_assigned: {
    label: 'Reset Assigned Amounts',
    description: "Set every category's assigned amount for this month to zero.",
  },
}

export const AUTO_STRATEGY_ORDER: AssignStrategy[] = [
  'underfunded',
  'target_amount',
  'last_month_assigned',
  'last_month_spent',
  'average_assigned',
  'average_spent',
]

export const RESET_STRATEGY_ORDER: AssignStrategy[] = [
  'reduce_overfunded',
  'reset_available',
  'reset_assigned',
]
