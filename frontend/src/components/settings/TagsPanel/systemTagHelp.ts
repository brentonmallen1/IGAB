/**
 * What each system tag does — the one place it is written down for the user.
 *
 * The tags themselves are seeded from `SYSTEM_TAGS` in
 * backend/src/igab/repositories/tag_repo.py, in this order; the effects are
 * in domain/activity_class.py (savings, long-term expense, debt principal),
 * the Subscriptions report (subscription) and TransactionRepository
 * .essential_spend (essential). Presentation only: nothing here decides how
 * money is counted, it says how it is.
 */
export const SYSTEM_TAG_HELP: { key: string; name: string; on: string; does: string }[] = [
  {
    key: 'subscription',
    name: 'Subscription',
    on: 'payees',
    does: 'The Subscriptions report totals charges to these payees — what recurs, and what cancelling would save.',
  },
  {
    key: 'savings',
    name: 'Savings',
    on: 'categories',
    does: 'Money leaving a Savings category counts as saving, not spending: it feeds the Savings report and the savings rate, and stays out of burn rate and the spending charts.',
  },
  {
    key: 'long_term_expense',
    name: 'Long-term expense',
    on: 'categories',
    does: 'Counted like Savings — money set aside for a known future cost (a sinking fund), not spent this month.',
  },
  {
    key: 'debt_principal',
    name: 'Debt principal',
    on: 'categories',
    does: 'Payments from these categories count as paying down debt rather than spending.',
  },
  {
    key: 'essential',
    name: 'Essential',
    on: 'categories and payees',
    does: 'Spending here is what a lean month costs. The Essentials report, the Overview’s essentials card and the Guide’s emergency-fund target are all built from it.',
  },
]
