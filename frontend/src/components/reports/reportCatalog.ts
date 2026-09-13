import type { ReportTab } from '../../stores/reportStore'
import type { ReportAccountScope } from './reportScope'

/**
 * What each report is, what it counts, and which accounts it reads — stated
 * once.
 *
 * The Reports overview dialog lists these, and every report's
 * `<ReportScopeNote>` reads its scope from here, so the accounts line in a
 * report's ⓘ popover and the overview's Accounts column cannot disagree.
 * `Record<ReportTab, …>` is what keeps this in step with `REPORT_TABS`: a new
 * tab without an entry does not typecheck.
 *
 * Copy follows what the server does, not what a report's title suggests —
 * see `report_service.py`, `report_basics.py` and `domain/activity_class.py`.
 * One sentence per field.
 */
export interface ReportCatalogEntry {
  scope: ReportAccountScope
  /** What the report is for. */
  summary: string
  /** The money it counts. */
  counts: string
  /** What a reader might expect to see and will not. */
  leavesOut: string
}

/** A report drawn inside another report's tab, with its own scope. */
export type ReportSectionId = 'payday-effect'

export interface ReportSectionEntry extends ReportCatalogEntry {
  label: string
  tab: ReportTab
}

export const REPORT_CATALOG: Record<ReportTab, ReportCatalogEntry> = {
  overview: {
    scope: 'overview',
    summary:
      'A snapshot: savings rate, expenses, burn rate, days until zero, essentials, your means.',
    counts:
      'Savings rate is savings ÷ income; days until zero is cash ÷ daily burn; your means is spending plus debt payments against income.',
    leavesOut:
      'Transfers between budget accounts, and investment growth — cards, loans and investments are not cash on hand.',
  },
  'net-worth': {
    scope: 'all-accounts',
    summary: 'Assets minus liabilities, month by month.',
    counts: 'Every account balance plus manually tracked assets and debts.',
    leavesOut: 'Nothing is filtered — a transfer between your own accounts never changes it.',
  },
  'account-composition': {
    scope: 'all-accounts',
    summary: 'How your balances split across account types over time.',
    counts:
      'Every account balance by type, assets above zero and debts below, netting to net worth.',
    leavesOut: 'Nothing is filtered — the Net line matches the Net Worth report.',
  },
  liabilities: {
    scope: 'liabilities',
    summary: 'Every tracked debt in one rollup, with payoff projections.',
    counts: 'Tracked liabilities, and payments as transfers into their loan accounts.',
    leavesOut: 'Debts you have not added as a liability; tags and activity classes play no part.',
  },
  savings: {
    scope: 'categories',
    summary: 'Balances and assignments of your savings envelopes.',
    counts:
      'Envelopes tagged Savings or Long-term expense — their Available and what was assigned.',
    leavesOut: 'Untagged envelopes, and the activity class of the transactions inside them.',
  },
  'savings-rate': {
    scope: 'on-budget',
    summary: 'How much of what came in you kept, month by month.',
    counts:
      'Savings — including transfers to tracked accounts marked as savings — ÷ income, plus debt principal when included.',
    leavesOut:
      'Transfers between budget accounts, spending, investment growth and interest inside tracked accounts.',
  },
  essentials: {
    scope: 'on-budget',
    summary: 'What a lean month costs; the headline is the last 90 days ÷ 3.',
    counts: 'Spending and debt payments in categories tagged Essential, or bound in the Guide.',
    leavesOut: 'Savings-tagged envelopes, and everything not tagged Essential.',
  },
  'cost-of-living': {
    scope: 'on-budget',
    summary:
      'Everything committed each month, in Essential and Non-essential tiers, against income.',
    counts:
      'Categories tagged Essential or Cost of living, plus every debt-principal payment, vs average income.',
    leavesOut: 'Untagged discretionary spending and savings.',
  },
  'emergency-fund': {
    scope: 'emergency-fund',
    summary: 'How many months of essentials your emergency fund would cover.',
    counts: 'The fund balance ÷ a three-month average of essentials, against a 3–6 month target.',
    leavesOut: 'Non-essential spending — the target is a lean month, not a normal one.',
  },
  'income-expense': {
    scope: 'on-budget',
    summary: 'Income against expenses each month, with the net.',
    counts: 'Income, spending, savings and debt principal; net is income minus the other three.',
    leavesOut: 'Transfers between budget accounts, and activity inside tracked accounts.',
  },
  'income-sources': {
    scope: 'on-budget',
    summary: 'Income per payee, month by month.',
    counts: 'Rows read as income, including negative income such as a clawed-back paycheck.',
    leavesOut: 'Refunds, transfers, investment growth and money drawn from tracked accounts.',
  },
  wishlist: {
    scope: 'wishlist',
    summary: 'What the cooling-off period did to what you wanted.',
    counts:
      'Every wish, open or closed, all time — resisted, bought after waiting, or bought early.',
    leavesOut: 'Purchases that never went on the wishlist.',
  },
  'burn-rate': {
    scope: 'on-budget',
    summary: 'Average monthly spending over rolling 30- and 90-day windows.',
    counts: 'Spending only.',
    leavesOut: 'Savings, debt payments and transfers.',
  },
  'cash-flow': {
    scope: 'on-budget-filterable',
    summary: 'A Sankey of income flowing into spending, spent or budgeted.',
    counts: 'Income into spending by group, with separate savings and debt trunks.',
    leavesOut: 'Transfers between budget accounts.',
  },
  projection: {
    scope: 'cash-projection',
    summary: 'A simulated range for your cash balance in the months ahead.',
    counts: 'Recent net flows, scheduled transactions and subscriptions, on cash accounts.',
    leavesOut: 'Credit cards and off-budget accounts.',
  },
  'budget-actual': {
    scope: 'categories',
    summary: 'What you assigned to each category against what you spent.',
    counts: 'Assigned vs spent, where spent includes outflows from Savings-tagged envelopes.',
    leavesOut:
      'Refunds do not reduce spent; money moved out of an envelope lowers its plan instead.',
  },
  'category-history': {
    scope: 'categories',
    summary: "One category's assigned, spent and available, month by month.",
    counts: "The budget page's own figures for each month.",
    leavesOut: 'Nothing is re-derived — other categories are one pick away.',
  },
  variance: {
    scope: 'categories',
    summary: 'The running total of assigned minus spent.',
    counts:
      'Assigned vs spent each month, where spent includes outflows from Savings-tagged envelopes.',
    leavesOut: 'Refunds do not reduce spent.',
  },
  volatility: {
    scope: 'categories',
    summary: 'How much each category swings month to month.',
    counts: 'Every categorized outflow, whatever its class — savings and debt outflows appear.',
    leavesOut: 'Uncategorized rows, and categories with fewer than two months of data.',
  },
  'spending-trends': {
    scope: 'categories',
    summary: 'Spending month by month in the categories you choose.',
    counts: 'Spending only, unless you include savings and debt payments.',
    leavesOut:
      'Transfers, and savings and debt payments unless you include them — a note says how much.',
  },
  'spending-breakdown': {
    scope: 'categories',
    summary: "Where the period's spending went, by group then category.",
    counts: 'Spending only, unless you include savings and debt payments.',
    leavesOut: 'Transfers, and savings and debt payments unless you include them.',
  },
  pareto: {
    scope: 'on-budget-filterable',
    summary: 'Where spending concentrates — the 80/20 view.',
    counts:
      'Spending only by group, category or payee, unless you include savings and debt payments.',
    leavesOut: 'Transfers, and savings and debt payments unless you include them.',
  },
  treemap: {
    scope: 'on-budget-filterable',
    summary: 'Spending as rectangles sized by amount.',
    counts: 'Spending only by group or category, unless you include savings and debt payments.',
    leavesOut: 'Transfers, and savings and debt payments unless you include them.',
  },
  seasonality: {
    scope: 'categories',
    summary: 'A category × month heatmap of spending peaks.',
    counts: 'Every categorized outflow, whatever its class — savings and debt outflows appear.',
    leavesOut: 'Uncategorized rows.',
  },
  subscriptions: {
    scope: 'on-budget',
    summary: 'What your subscriptions cost, monthly and annually.',
    counts: 'Charges in Subscription-tagged categories, per category and per payee.',
    leavesOut: 'Untagged categories and the month in progress.',
  },
  'plan-reality': {
    scope: 'categories',
    summary: "Each month's plan against that month's spending, ignoring carryover.",
    counts:
      'Assigned vs spent per category-month, where spent includes outflows from Savings-tagged envelopes.',
    leavesOut: 'Carryover from earlier months, and refunds do not reduce spent.',
  },
  anomalies: {
    scope: 'categories',
    summary: 'Category-months well above or below their usual spending.',
    counts: 'Every categorized outflow, whatever its class — savings and debt outflows appear.',
    leavesOut: 'Uncategorized rows.',
  },
  payees: {
    scope: 'on-budget-filterable',
    summary: 'Your top payees by spending, and which ones recur.',
    counts: 'Spending only, per payee.',
    leavesOut: 'Savings, debt payments and transfers.',
  },
  'day-patterns': {
    scope: 'on-budget-filterable',
    summary: 'Spending by day of the week.',
    counts: 'Spending only.',
    leavesOut: 'Savings, debt payments and transfers.',
  },
  timeline: {
    scope: 'on-budget-filterable',
    summary: 'Your largest transactions, newest first.',
    counts: 'Spending and income, with savings and debt payments labelled apart.',
    leavesOut: 'Transfers between budget accounts.',
  },
}

export const REPORT_SECTIONS: Record<ReportSectionId, ReportSectionEntry> = {
  'payday-effect': {
    label: 'Payday Effect',
    tab: 'day-patterns',
    scope: 'on-budget',
    summary: 'Spending in the days after each payday against your baseline.',
    counts:
      'Spending only, around paydays: income deposits of a minimum amount into cash accounts.',
    leavesOut: 'Subscriptions, and transfers or card credits as paydays.',
  },
}

/** The scope a report — or a section drawn inside one — states. */
export function reportScopeOf(report: ReportTab | ReportSectionId): ReportAccountScope {
  return report in REPORT_SECTIONS
    ? REPORT_SECTIONS[report as ReportSectionId].scope
    : REPORT_CATALOG[report as ReportTab].scope
}
