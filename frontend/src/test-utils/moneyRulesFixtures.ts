/** Served shapes for the money tab's tests. Wording is invented on purpose:
 * a test that passes on it proves the component rendered what was served. */
import type { MoneyRule, MoveExplanation } from '../api/moneyRules'

export const SERVED_RULES: MoneyRule[] = [
  {
    position: 1,
    cls: 'savings',
    class_label: 'Served Savings',
    reason: 'tagged_savings',
    reason_text: 'served tag reason',
    tag_key: 'savings',
    is_default: false,
  },
  {
    position: 2,
    cls: 'transfer_internal',
    class_label: 'Served Transfer',
    reason: 'internal_transfer',
    reason_text: 'served transfer reason',
    tag_key: null,
    is_default: false,
  },
  {
    position: 3,
    cls: 'spending',
    class_label: 'Served Spending',
    reason: 'default_spending',
    reason_text: 'served default reason',
    tag_key: null,
    is_default: true,
  },
]

export const ZERO_FIGURES = {
  income: 0,
  spending: 0,
  cost_of_living: 0,
  savings: 0,
  debt_principal: 0,
  savings_rate: null,
  savings_rate_with_debt: null,
}

export function explanation(over: Partial<MoveExplanation> = {}): MoveExplanation {
  return {
    category_role: 'to',
    category_applied: true,
    legs: [
      {
        role: 'from',
        on_budget: false,
        amount: -1000,
        category: 'none',
        cls: 'transfer_internal',
        class_label: 'Served Transfer',
        reason: 'internal_transfer',
        reason_text: 'served far-side reason',
        counted_in: [],
        planned_spend_by_tag: false,
      },
      {
        role: 'to',
        on_budget: true,
        amount: 1000,
        category: 'none',
        cls: 'income',
        class_label: 'Served Income',
        reason: 'uncategorized_inflow',
        reason_text: 'served income reason',
        counted_in: ['income'],
        planned_spend_by_tag: false,
      },
    ],
    budget_terms: [{ term: 'ready_to_assign', delta: 1000 }],
    class_totals: { income: 1000 },
    figures: { ...ZERO_FIGURES, income: 1000 },
    net_worth_delta: 0,
    assumption: 'Served assumption.',
    ...over,
  }
}
