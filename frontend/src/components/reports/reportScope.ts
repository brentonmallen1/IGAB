/**
 * Which accounts a report considers, in words.
 *
 * Pure so the report catalog (`reportCatalog.ts`) can name a report's scope
 * without importing a component. Named `ReportAccountScope` rather than
 * `ReportScope` because that name already belongs to the filter bar's
 * category/tag/saved-filter scope in `api/reports.ts`.
 */
export type ReportAccountScope =
  | 'all-accounts'
  | 'on-budget'
  | 'on-budget-filterable'
  | 'categories'
  | 'cash-projection'
  | 'liabilities'
  | 'overview'
  | 'emergency-fund'
  | 'wishlist'

/** The sentence after "Accounts:" — the info popovers prefix it, the Reports
 *  overview puts it under an Accounts column. */
export const SCOPE_COPY: Record<ReportAccountScope, string> = {
  'all-accounts': 'every account counts — on-budget, tracking, and loans.',
  'on-budget':
    'on-budget only. Plain activity inside tracking accounts ' +
    '(investments, loans) never appears here — categorized transfers to them do.',
  'on-budget-filterable':
    'on-budget by default — plain activity inside tracking accounts ' +
    "doesn't count, categorized transfers to them do. Picking accounts in the " +
    'filter bar overrides this, tracking accounts included.',
  categories:
    'follows categories, not accounts — anything categorized counts, ' +
    "matching the budget page's envelope math.",
  'cash-projection': 'open, on-budget accounts only.',
  liabilities:
    'driven by your tracked liabilities, not account types — add a ' +
    'liability (or link one to a loan account) to include a debt here.',
  overview:
    'net worth spans every account; the income, spending, and burn ' +
    'metrics count on-budget accounts only.',
  'emergency-fund':
    'whatever the Guide reads as your emergency fund — the envelopes or ' +
    'accounts it is bound to, plus any amount you told it you keep elsewhere.',
  wishlist: 'none — it reads your wishlist, not transactions.',
}
