/**
 * What each system tag does — the one place it is written down for the user.
 *
 * The tags themselves are seeded from `SYSTEM_TAGS` in
 * backend/src/igab/repositories/tag_repo.py, and both lists are tested against
 * shared/system_tags.json, so a tag seeded there cannot ship unexplained here.
 * The effects are in domain/activity_class.py (savings, debt principal), the
 * Savings report (long-term expense: membership only,
 * services/savings_report.py — it no longer classifies anything), the
 * Subscriptions report (subscription, categories only —
 * CATEGORY_ONLY_SYSTEM_KEYS in tag_repo.py) and TransactionRepository
 * .essential_spend (essential, cost of living). Presentation only: nothing
 * here decides how money is counted, it says how it is.
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
    does: 'Money set aside. Each Savings category counts in one of two ways. Sent out: money leaving the envelope counts as saved, not spending — for an envelope that feeds an investment, a retirement account or another bank. Kept here: the envelope’s balance is the savings — assigning to it counts as saved, spending from it is spending and lowers what you saved, and moving it to an off-budget savings account changes nothing. Either way it feeds the Savings report and the savings rate, and still counts against what you assigned, so Budget vs Actual shows the envelope being spent down.',
  },
  {
    key: 'emergency_fund',
    name: 'Emergency fund',
    on: 'categories',
    does: 'Money set aside for genuine surprises, chosen by you and never guessed. It counts as savings (kept here unless you change it). The emergency fund is these envelopes’ Available, plus the off-budget accounts you mark Counts toward emergency fund, plus anything you say you keep elsewhere. Sent out or kept here changes your savings rate, never the fund’s total.',
  },
  {
    key: 'long_term_expense',
    name: 'Long-term expense',
    on: 'categories',
    does: 'A sinking fund — money set aside monthly toward a planned, irregular bill: insurance, property tax, a trip. Never savings and never the emergency fund: the bill counts as spending when you pay it, and the Savings report lists the envelope under Sinking funds, apart from Saved. Tagged Essential too, its bills are spread over 12 months in the essentials figures unless you turn that off. A category tagged Savings as well counts as savings instead.',
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
    on: 'categories',
    does: 'Spending here is what a lean month costs — what you could not cut. The Essentials report, the Overview’s essentials card, the Guide’s emergency-fund target and the Essentials tier of the Cost of Living report are all built from it. If the Guide has categories bound to Essential expenses, those win; otherwise the tag decides. With neither, the reports show no Essentials figure and the Guide uses all your spending.',
  },
  {
    key: 'cost_of_living',
    name: 'Cost of living',
    on: 'categories',
    does: 'Committed but not strictly necessary — a subscription, a gym, a membership you would cancel in a genuine emergency but pay every month otherwise. The Cost of Living report counts it together with your Essential categories and your debt payments; the gap between that and Essentials alone is what a lean month could shed.',
  },
  {
    key: 'wishlist',
    name: 'Wishlist',
    on: 'categories',
    does: 'Applied by the wishlist itself to every envelope that funds an open wish, and removed when none does — nothing to tag by hand. Reports and tag filters can read it.',
  },
]
