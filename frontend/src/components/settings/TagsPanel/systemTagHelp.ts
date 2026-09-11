/**
 * What each system tag does — the one place it is written down for the user.
 *
 * The tags themselves are seeded from `SYSTEM_TAGS` in
 * backend/src/igab/repositories/tag_repo.py, in this order; the effects are
 * in domain/activity_class.py (savings, long-term expense, debt principal),
 * the Subscriptions report (subscription, categories only —
 * CATEGORY_ONLY_SYSTEM_KEYS in tag_repo.py) and TransactionRepository
 * .essential_spend (essential). Presentation only: nothing here decides how
 * money is counted, it says how it is.
 */
export const SYSTEM_TAG_HELP: { key: string; name: string; on: string; does: string }[] = [
  {
    key: 'subscription',
    name: 'Subscription',
    on: 'categories',
    does: 'Every charge filed to one of these categories is a subscription; the Subscriptions report lists them by payee — what recurs, and what cancelling would save. It used to sit on payees; a payee never tagged simply vanished from the report.',
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
    does: 'Marks a sinking fund — money set aside monthly toward a known annual bill. It appears in the Savings report beside your savings, and the bill itself still counts as spending when you pay it.',
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
    does: 'Spending here is what a lean month costs. The Essentials report, the Overview’s essentials card and the Guide’s emergency-fund target are all built from it. If the Guide has categories bound to Essential expenses, those win; otherwise the tag decides; with neither, every spending row counts.',
  },
  {
    key: 'wishlist',
    name: 'Wishlist',
    on: 'categories',
    does: 'Applied by the wishlist itself to every envelope that funds an open wish, and removed when none does — nothing to tag by hand. Reports and tag filters can read it.',
  },
]
