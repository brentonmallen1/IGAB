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

/**
 * What no report counts as money in or out, whatever its own row says —
 * stated once, above the table, rather than in every row's Leaves out. Two
 * rules in `domain/activity_class.py`: a starting balance, or an unfiled row
 * from before an account's budget start date, is where that account's
 * counting begins (rules 1 and 4); and money arriving on a card with no
 * category pays the card down (rule 10).
 */
export const NEVER_COUNTED =
  'No report counts a starting balance, or anything uncategorized from before an account’s budget start date, as income or spending — that is where the account’s counting begins. Money arriving on a credit card with no category is never income: it pays the card down.'

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
      'A snapshot: savings rate, expenses, burn rate, days until zero, essentials, your means and its trend.',
    counts:
      'Savings rate is savings ÷ income; days until zero is cash ÷ daily burn; your means is spending plus debt payments against income, and its trend reads the last 12 complete months.',
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
    scope: 'savings',
    summary: 'What you have saved, what is on the way to savings, and your sinking funds.',
    counts:
      'Saved: Savings and Emergency fund envelopes that count while money is in the budget, plus off-budget savings accounts; on the way: Savings envelopes that count when money leaves the budget; sinking funds: Long-term expense envelopes with their targets.',
    leavesOut:
      'On-budget accounts, and untagged envelopes — the three parts are never added together.',
  },
  'savings-rate': {
    scope: 'on-budget',
    summary: 'How much of what came in you kept, month by month.',
    counts:
      'Saved — money moved to savings, including transfers to tracked accounts that count as savings, plus what Savings envelopes that count while money is in the budget came to hold — ÷ income, plus debt principal when included.',
    leavesOut:
      'Transfers between budget accounts, spending, investment growth and interest inside tracked accounts.',
  },
  essentials: {
    scope: 'on-budget',
    summary:
      'What a lean month costs; the headline is the last 90 days ÷ 3, with yearly Long-term expense bills spread over 12 months when that is on.',
    counts: 'Spending and debt payments in categories tagged Essential.',
    leavesOut: 'Money that counts as saved, and everything not tagged Essential.',
  },
  'cost-of-living': {
    scope: 'on-budget',
    summary:
      'Everything committed each month, in Essential and Non-essential tiers, against income.',
    counts:
      'Categories tagged Essential or Cost of living, plus every debt-principal payment, vs average income.',
    leavesOut: 'Savings, and untagged spending — that is the Discretionary report.',
  },
  discretionary: {
    scope: 'on-budget',
    summary:
      'What you chose to spend: spending outside Essential and Cost of living, by category and month.',
    counts:
      'Spending in categories tagged neither Essential nor Cost of living, net of refunds, and uncategorized spending on its own line.',
    leavesOut:
      'Everything Cost of Living counts, savings, debt payments and transfers; with nothing tagged, it shows no figure at all.',
  },
  'emergency-fund': {
    scope: 'emergency-fund',
    summary: 'How many months of essentials your emergency fund would cover.',
    counts:
      'The fund balance ÷ a three-month average of essentials (yearly Long-term expense bills spread over 12 months when that is on), against a 3–6 month target.',
    leavesOut: 'Non-essential spending — the target is a lean month, not a normal one.',
  },
  'income-expense': {
    scope: 'on-budget',
    summary: 'Income against expenses each month, with the net.',
    counts:
      'Income, spending, saved and debt principal; net is income minus spending, money moved to savings and debt principal — money held in an envelope never left.',
    leavesOut: 'Transfers between budget accounts, and activity inside tracked accounts.',
  },
  'income-sources': {
    scope: 'on-budget',
    summary: 'Income per payee, month by month.',
    counts: 'Rows read as income, including negative income such as a clawed-back paycheck.',
    leavesOut:
      'Refunds, transfers, uncategorized credits on a card, investment growth and money drawn from tracked accounts.',
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
    summary: 'Spending over the last 30 days against the 60 days before them, month by month.',
    counts: 'Spending only, net of refunds; the prior 60 days are averaged per 30.',
    leavesOut: 'Savings, debt payments and transfers.',
  },
  'cash-flow': {
    scope: 'on-budget-filterable',
    summary: 'Where the money went: what came in, and where it went, spent or budgeted.',
    counts:
      'Income, refunds, money drawn from savings and borrowing on the left; spending by group, money moved to savings accounts and debt payments on the right — each net, with Left over or Shortfall making the two sides equal.',
    leavesOut: 'Transfers between budget accounts, and starting balances.',
  },
  projection: {
    scope: 'cash-projection',
    summary: 'Where your cash balance lands if things carry on, as a range of likely paths.',
    counts:
      'Your recent cash in and out — paychecks included — replayed a few weeks at a time, plus scheduled transactions and subscriptions, on cash accounts.',
    leavesOut: 'Credit cards, off-budget accounts, and starting balances.',
  },
  'budget-actual': {
    scope: 'categories',
    summary: 'What you assigned to each category against what you spent.',
    counts:
      'Assigned vs spent, where spent includes outflows from Savings and Emergency fund envelopes.',
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
      'Assigned vs spent each month, where spent includes outflows from Savings and Emergency fund envelopes.',
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
    counts:
      'Spending only, net of refunds, with uncategorized spending as its own line; the average is over complete months. Include savings and debt payments to add them.',
    leavesOut:
      'Transfers, and savings and debt payments unless you include them — a note says how much.',
  },
  'spending-breakdown': {
    scope: 'categories',
    summary: "Where the period's spending went, by group then category.",
    counts:
      'Spending only, net of refunds, with uncategorized spending as its own line, unless you include savings and debt payments.',
    leavesOut: 'Transfers, and savings and debt payments unless you include them.',
  },
  pareto: {
    scope: 'on-budget-filterable',
    summary: 'Where spending concentrates — the 80/20 view.',
    counts:
      'Spending only by group, category or payee, net of refunds, with uncategorized spending as its own line, unless you include savings and debt payments.',
    leavesOut: 'Transfers, and savings and debt payments unless you include them.',
  },
  treemap: {
    scope: 'on-budget-filterable',
    summary: 'Spending as rectangles sized by amount.',
    counts:
      'Spending only by group or category, net of refunds, with uncategorized spending as its own line, unless you include savings and debt payments.',
    leavesOut:
      'Transfers, savings and debt payments unless you include them, and any line whose refunds outweigh its spending — it has no area to draw.',
  },
  seasonality: {
    scope: 'categories',
    summary: 'A category × month heatmap of spending peaks, shaded within each category.',
    counts:
      'Spending only, net of refunds, with uncategorized spending as its own line, over complete months, unless you include savings and debt payments.',
    leavesOut: 'The month in progress, and all but the 20 largest categories.',
  },
  subscriptions: {
    scope: 'on-budget',
    summary: 'What your subscriptions cost, monthly and annually.',
    counts:
      'Charges less refunds in Subscription-tagged categories over the last 12 complete months, per category and per service.',
    leavesOut: 'Untagged categories, and services with no charge for one and a half cycles.',
  },
  'plan-reality': {
    scope: 'categories',
    summary: "Each month's plan against that month's spending, ignoring carryover.",
    counts:
      'Assigned vs spent per category-month, where spent includes outflows from Savings and Emergency fund envelopes.',
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
    counts:
      'Spending only, per payee, net of refunds; a purchase split across envelopes counts once.',
    leavesOut: 'Savings, debt payments, transfers, and spending with no payee.',
  },
  'day-patterns': {
    scope: 'on-budget-filterable',
    summary: 'An average day of each weekday, by the bank posting date.',
    counts: 'Spending only, net of refunds, divided by how many of each weekday the range holds.',
    leavesOut: 'Savings, debt payments and transfers.',
  },
  timeline: {
    scope: 'on-budget-filterable',
    summary: 'Your largest transactions, newest first — money out unless you choose All.',
    counts: 'Spending and income, with savings and debt payments labelled apart.',
    leavesOut: 'Transfers between budget accounts.',
  },
}

export const REPORT_SECTIONS: Record<ReportSectionId, ReportSectionEntry> = {
  'payday-effect': {
    label: 'Payday Effect',
    tab: 'day-patterns',
    scope: 'on-budget',
    summary: "The median payday's spending on each day after it, against a typical day.",
    counts:
      'Discretionary spending only, net of refunds, around paydays: income deposits of a minimum amount into cash accounts.',
    leavesOut:
      'Essential and Cost of living categories, subscriptions, and transfers or card credits as paydays.',
  },
}

/** The scope a report — or a section drawn inside one — states. */
export function reportScopeOf(report: ReportTab | ReportSectionId): ReportAccountScope {
  return report in REPORT_SECTIONS
    ? REPORT_SECTIONS[report as ReportSectionId].scope
    : REPORT_CATALOG[report as ReportTab].scope
}
