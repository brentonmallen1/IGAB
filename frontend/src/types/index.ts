export interface User {
  id: string
  email: string
  display_name: string | null
  is_admin: boolean
}

export type NumberFormat = 'comma_dot' | 'dot_comma' | 'space_comma'
export type DateFormat = 'mdy' | 'dmy' | 'ymd'
export type TimeFormat = '12h' | '24h'

export interface Budget {
  id: string
  name: string
  /** The caller's role in this budget — drives sharing affordances. */
  role?: 'owner' | 'member' | null
  currency_code: string
  number_format: NumberFormat
  date_format: DateFormat
  time_format: TimeFormat
}

export interface Account {
  id: string
  budget_id: string
  name: string
  account_type: AccountType
  on_budget: boolean
  classification: AccountClassification | null
  is_closed: boolean
  sort_order: number
  note: string | null
  simplefin_account_id: string | null
  simplefin_account_name: string | null
  simplefin_sync_enabled: boolean
  first_sync_complete: boolean
  last_simplefin_sync_at: string | null
  simplefin_balance: number | null
  balance: number
  cleared_balance: number
  uncleared_balance: number
  last_reconciled_at: string | null
  /** Always sent (may be null) — the balance the last reconciliation locked. */
  last_reconciled_balance: number | null
  uncategorized_count: number
  created_at: string
  updated_at: string
}

// Account types are per-budget registry keys now (built-ins seeded for every
// budget plus user-defined custom types) — see api/accountTypes.ts. Built-in
// keys: checking, savings, cash, credit_card, loan, investment, other_asset,
// other_liability.
export type AccountType = string
export type AccountClassification = 'asset' | 'liability'

export interface CategoryGroup {
  id: string
  budget_id: string
  name: string
  sort_order: number
  is_hidden: boolean
  is_system: boolean
}

export interface TagSimple {
  id: string
  name: string
  color_slot: 'red' | 'orange' | 'yellow' | 'green' | 'teal' | 'blue' | 'purple' | 'pink' | null
}

export interface Category {
  id: string
  category_group_id: string
  budget_id: string
  name: string
  subtitle: string | null
  sort_order: number
  note: string | null
  is_hidden: boolean
  linked_account_id: string | null
  /** The liability that owns this category, if any. */
  linked_liability_id: string | null
  /**
   * May money be budgeted or moved into this envelope? Computed by the server
   * from `IS_ASSIGNABLE` (backend/src/igab/repositories/category_filters.py).
   * Never rebuild it here: six components each spelled their own version and
   * they disagreed about system groups, hidden groups and linked categories.
   */
  is_assignable: boolean
  /**
   * May a transaction leg be filed here? Differs from `is_assignable` on
   * system groups — income is filed into one, so excluding them here would
   * remove the only place a paycheque can go.
   */
  is_categorizable: boolean
  tags?: TagSimple[]
  created_at: string
  updated_at: string
}

export interface BudgetFilter {
  id: string
  budget_id: string
  name: string
  sort_order: number
  category_ids: string[]
  created_at: string
  updated_at: string
}

export interface BudgetViewGroup {
  id: string
  name: string
  sort_order: number
}

export interface BudgetViewPlacement {
  category_id: string
  /** null = placed in the view but in no group; shown under Unassigned. */
  group_id: string | null
  sort_order: number
  is_hidden: boolean
}

/** A different arrangement of the same categories. Unlike a BudgetFilter,
 *  which narrows the set, a view regroups it — and never edits the budget's
 *  own category groups. */
export interface BudgetView {
  id: string
  budget_id: string
  name: string
  sort_order: number
  /** Drop categories this view hasn't placed, instead of collecting them under
   *  Unassigned. Off by default so a newly added category surfaces. */
  hide_unassigned: boolean
  groups: BudgetViewGroup[]
  placements: BudgetViewPlacement[]
  created_at: string
  updated_at: string
}

/** The three answers the budget row's pill can show. Mirrors
 *  `TargetStatus` in backend/src/igab/domain/enums.py. */
export type TargetStatus = 'funded' | 'underfunded' | 'overfunded'

export interface CategoryBalance {
  category_id: string
  month: string
  assigned: number
  activity: number
  available: number
  /**
   * The target verdict, computed by the server's TargetService — the same
   * function Fill Underfunded asks. `null` when the category has no target.
   *
   * Never re-derive this. utils/targets.ts used to mirror `calculate_status`
   * and CategoryRow re-implemented the shortfall a third time with the target
   * types inverted relative to the mirror, so the pill and the "Save $X more"
   * line rendered beside it were computed from different rules.
   */
  target_status: TargetStatus | null
  /**
   * What still has to be assigned this month for the target to be met, and
   * exactly what Fill Underfunded would move. `null` when there is no target.
   */
  needed_this_month: number | null
}

export interface BudgetMonth {
  month: string
  to_be_assigned: number
  total_assigned: number
  total_activity: number
  total_overspent: number
  /** How many categories make up `total_overspent`, counted server-side in the
   *  same loop — so the count and the amount are always about the same set,
   *  and both match what Cover Overspent will act on. */
  overspent_count: number
  /** Committed to months after this one; already deducted from to_be_assigned */
  assigned_in_future: number
  category_balances: CategoryBalance[]
}

export interface BudgetTransactionsResponse {
  transactions: Transaction[]
  total_count: number
  /** Decimal serialized as string; totals cover the full filter match, not just the page */
  total_amount: string
}

export interface Transaction {
  id: string
  budget_id: string
  account_id: string
  date: string
  /** The user's originally-entered date when bank data overwrote `date` */
  entered_date: string | null
  /** The bank's posted date; `date` stays the user's ledger date */
  bank_posted_date: string | null
  amount: number
  /** The bank's own amount, kept verbatim; `amount` is the ledger value */
  bank_amount: number | null
  /** The bank's own payee string before it was resolved to a payee */
  bank_payee: string | null
  payee_id: string | null
  category_id: string | null
  /**
   * Does the user still have to file this row? Computed by the server from
   * `NEEDS_CATEGORY` (backend/src/igab/repositories/txn_filters.py) — the
   * single definition of the rule. Never re-derive it here: this file once
   * carried a second implementation and the two disagreed, drawing ~930 rows
   * as unfiled under a badge that counted 3.
   */
  needs_category: boolean
  /** The account on the other side of a transfer, or null for a plain
   *  transaction. Server-computed — COUNTERPART_ACCOUNT_ID in backend
   *  txn_filters.py — because a linked leg's payee can be null or wrong.
   *  Render via utils/transferDisplay.ts; never re-derive. */
  counterpart_account_id: string | null
  memo: string | null
  cleared: ClearedStatus
  approved: boolean
  transfer_id: string | null
  parent_transaction_id: string | null
  is_split: boolean
  import_id: string | null
  import_description: string | null
  sync_id: string | null
  sync_source: string | null
  /** AI provenance: 'ai_receipt' | 'ai_nl'; null for manual/import/sync rows */
  created_via: string | null
  has_sync_source: boolean
  created_at: string
  updated_at: string
}

export type ClearedStatus = 'pending' | 'uncleared' | 'cleared' | 'reconciled'

/** Per-item outcome of a bulk transaction action */
export interface BulkActionResult {
  updated: string[]
  failed: Array<{ id: string; reason: string }>
  /** Change-log batch id for undo (null if nothing was updated). */
  batch_id: string | null
}

/** DELETE /transactions/{id} response (was 204, now returns batch for undo). */
export interface DeleteTransactionResult {
  batch_id: string
}

export interface Payee {
  id: string
  budget_id: string
  name: string
  default_category_id: string | null
  transfer_account_id: string | null
  mapping_samples: string | null
  /** Regex applied to incoming raw payee names; a match assigns this payee */
  match_pattern: string | null
  tags?: TagSimple[]
}

export interface TransactionCreate {
  account_id: string
  date: string
  amount: number
  payee_id?: string
  payee_name?: string
  category_id?: string
  memo?: string
  cleared?: ClearedStatus
  approved?: boolean
  transfer_account_id?: string
  splits?: SplitCreate[]
  /** Links the created transaction to the AI job that drafted it (NL entry);
   * the server derives created_via from the job. */
  ai_job_id?: string
  /** Opt-in mobile capture (both or neither) — powers nearby-payee suggestions */
  latitude?: number
  longitude?: number
}

export interface SplitCreate {
  amount: number
  category_id?: string
  payee_id?: string
  payee_name?: string
  memo?: string
}

export interface SpendingCategory {
  id: string
  name: string
  group_name: string
  total: number
  pct: number
}

export interface SpendingReport {
  categories: SpendingCategory[]
  total: number
}

export interface IncomeExpenseMonth {
  month: string
  income: number
  /** Money spent. Saving and debt principal are separate — both leave the
   *  budget, but neither is spending. */
  expenses: number
  savings: number
  debt_principal: number
  /** income - expenses - savings - debt_principal, so the parts reconcile. */
  net: number
}

export interface IncomeExpenseReport {
  months: IncomeExpenseMonth[]
}

export interface CategoryTarget {
  id: string
  category_id: string
  target_type: string
  target_amount: number
  target_date: string | null
  repeat_frequency: string | null
}

export interface ScheduledTransaction {
  id: string
  budget_id: string
  account_id: string
  amount: number
  payee_id: string | null
  category_id: string | null
  memo: string | null
  frequency: string
  start_date: string
  end_date: string | null
  auto_create: boolean
  days_before_reminder: number
  next_occurrence_date: string
  transfer_account_id: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface CategoryHistory {
  category_id: string
  last_month_assigned: number
  last_month_spent: number
  average_assigned: number
  average_spent: number
  months_included: number
}

export type AutoAssignAction =
  | 'last_month_assigned'
  | 'last_month_spent'
  | 'average_assigned'
  | 'average_spent'
  | 'reset'

/** Bulk strategies offered by the TBA hero's Assign dropdown */
export type AssignStrategy =
  | 'underfunded'
  | 'last_month_assigned'
  | 'last_month_spent'
  | 'average_assigned'
  | 'average_spent'
  | 'reduce_overfunded'
  | 'reset_available'
  | 'reset_assigned'

// ─── Report Types ───────────────────────────────────────────────────────────

export interface DashboardMetrics {
  to_be_assigned: number
  net_worth: number
  net_worth_prev: number
  burn_rate_30: number
  burn_rate_90: number
  /** null when no income was recorded in the window — a gap, not a floor.
   *  "No income" and "saved nothing" are different facts. */
  savings_rate: number | null
  days_until_zero: number | null
  income_this_month: number
  expenses_this_month: number
  expenses_prev_month: number
  top_categories: { id: string; name: string; group_name: string; total: number }[]
}

export interface NetWorthPoint {
  date: string
  total_assets: number
  total_liabilities: number
  net_worth: number
  unmanaged_liability_total: number
  accounts: {
    account_id: string
    account_name: string
    account_type: string
    classification: string | null
    balance: number
  }[]
}

export interface NetWorthReport {
  points: NetWorthPoint[]
  unmanaged_liability_total: number
}

export interface LiabilitiesReportItem {
  liability_id: string
  name: string
  liability_type: string
  mode: 'managed' | 'unmanaged'
  current_balance: number
  interest_rate: number | null
  baseline_payoff_date: string | null
  live_payoff_date: string | null
  /** Null when the terms are unset — no schedule, so no interest to project */
  total_interest_remaining: number | null
  never_pays_off: boolean
  terms_complete: boolean
}

export interface LiabilitiesBalancePoint {
  date: string
  per_liability: Record<string, number>
  total: number
}

export interface LiabilitiesReport {
  items: LiabilitiesReportItem[]
  total_balance: number
  /** Sums only the rows whose terms are known */
  total_interest_remaining: number
  /** How many rows were left out of that total */
  liabilities_missing_terms: number
  balance_over_time: LiabilitiesBalancePoint[]
}

export interface AccountCompositionPoint {
  date: string
  // Balance per account-type key present in the budget (custom types included)
  balances: Record<string, number>
}

export interface AccountCompositionReport {
  points: AccountCompositionPoint[]
}

export interface BurnRatePoint {
  date: string
  rolling_30: number
  rolling_90: number
}

export interface BurnRateReport {
  points: BurnRatePoint[]
}

export interface SankeyNode {
  id: string
  name: string
  type: 'income_payee' | 'budget' | 'category_group' | 'category' | 'expense_payee'
  /** The entity this node stands for. `id` is a display key that may compose
   *  several ids — a category node is keyed by (group, category) so one
   *  category can sit under both its own group and the savings trunk. */
  entity_id?: string | null
}

export interface SankeyLink {
  source: string
  target: string
  value: number
}

export interface CategoryPayee {
  name: string
  total: number
}

export interface CashFlowReport {
  nodes: SankeyNode[]
  links: SankeyLink[]
  total_income: number
  /** Everything that left the budget — the links off the budget node sum to
   *  this. `total_spending` + `total_savings` + `total_debt_principal` is how
   *  it splits; a card labelled "Expenses" must use the first, not this. */
  total_expense: number
  total_spending: number | string
  total_savings: number | string
  total_debt_principal: number | string
  category_payees: Record<string, CategoryPayee[]>
  group_categories: Record<string, CategoryPayee[]>
}

export interface BudgetActualItem {
  category_id: string
  category_name: string
  category_group_name: string
  assigned: number
  spent: number
  variance: number
  variance_pct: number
}

export interface BudgetActualReport {
  categories: BudgetActualItem[]
  total_assigned: number
  total_spent: number
}

export interface PlanRealityCell {
  month: string
  assigned: number
  spent: number
  variance: number
}

export interface PlanRealityCategory {
  category_id: string
  category_name: string
  category_group_name: string
  monthly: PlanRealityCell[]
  months_over: number
  months_active: number
  total_assigned: number
  total_spent: number
  avg_overspend: number
  chronic: boolean
}

export interface PlanRealityReport {
  months: string[]
  categories: PlanRealityCategory[]
  total_assigned: number
  total_spent: number
  chronic_count: number
}

export interface VariancePoint {
  month: string
  budget_assigned: number
  actual_spent: number
  monthly_variance: number
  cumulative_variance: number
}

export interface VarianceReport {
  points: VariancePoint[]
}

export interface VolatilityItem {
  category_id: string
  category_name: string
  category_group_name: string
  mean: number
  std_dev: number
  min_val: number
  max_val: number
  p25: number
  p75: number
  months_included: number
}

export interface VolatilityReport {
  categories: VolatilityItem[]
}

export interface SpendingGroupItem {
  id: string
  name: string
  parent_id: string | null
  parent_name: string | null
  total: number
  count: number
  pct: number
  children?: SpendingGroupItem[]
}

export interface SpendingClassExcluded {
  activity_class: string
  label: string
  categories: number
  total: number | string
}

export interface SpendingGroupedReport {
  groups: SpendingGroupItem[]
  total: number
  /** What the active view kept out: categories with spending in the window
   *  that the view hides. Zero without a view. Decimals arrive as strings —
   *  coerce before math. */
  view_hidden_categories: number
  view_hidden_total: number | string
  /** Savings / debt activity in categories the user is looking at that a
   *  spending report will not count. Empty without a selection or view. */
  class_excluded: SpendingClassExcluded[]
}

export interface CategoryClassSlice {
  activity_class: string
  label: string
  total: number | string
  count: number
}

export interface CategoryClassification {
  classes: CategoryClassSlice[]
  window_months: number
  dominant: string | null
  dominant_label: string | null
  explanation: string | null
}

export interface SeasonalityCell {
  category_id: string
  category_name: string
  month: string
  total: number
}

export interface SeasonalityReport {
  cells: SeasonalityCell[]
  months: string[]
  categories: { id: string; name: string }[]
}

export interface PayeeSpending {
  payee_id: string
  payee_name: string
  total: number
  count: number
  /** Share of the report's grand total, 0–100 */
  pct: number
  monthly_trend: { month: string; total: number }[]
  top_categories: { category_name: string; total: number }[]
  is_recurring: boolean
}

export interface PayeeAnalysisReport {
  payees: PayeeSpending[]
  total: number
}

export interface DayPatternItem {
  day_of_week: number
  day_name: string
  total: number
  count: number
  avg_transaction: number
}

export interface DayPatternsReport {
  days: DayPatternItem[]
  /** Savings / debt activity in the categories the user selected that this
   *  chart will not count. Empty without a selection. */
  class_excluded: SpendingClassExcluded[]
}

export interface TimelineTransaction {
  id: string
  date: string
  amount: number
  payee_name: string | null
  category_name: string | null
  memo: string | null
  /** What this row counts as — 'savings', 'debt_principal', 'income', etc.
   *  A large transfer into savings belongs on this timeline, but drawing it
   *  as an expense because the amount is negative would misreport it. */
  activity_class: string
  /** Its display label, served rather than mirrored — a local copy here had
   *  already drifted from the backend's wording. */
  activity_label: string
}

export interface TimelineReport {
  transactions: TimelineTransaction[]
}

export interface SubscriptionPayee {
  payee_id: string
  payee_name: string
  monthly_amounts: number[]
  total: number
  /** True monthly burden: total / months since first charge */
  avg_monthly: number
  /** Typical charge: total / charge count */
  avg_per_charge: number
  last_charge_date: string | null
  transaction_count: number
}

export interface SubscriptionsSummary {
  total_monthly: number
  total_annual: number
  active_count: number
}

export interface SubscriptionsReport {
  subscriptions: SubscriptionPayee[]
  summary: SubscriptionsSummary
  months: string[]
}

export interface SavingsCategory {
  category_id: string
  category_name: string
  group_name: string
  monthly_balances: number[]
  current_balance: number
  target_balance: number | null
  total_inflow: number
}

export interface SavingsSummary {
  total_balance: number
  total_inflow: number
  avg_monthly_inflow: number
  category_count: number
}

export interface SavingsReport {
  categories: SavingsCategory[]
  summary: SavingsSummary
  months: string[]
}

export interface AnomalyItem {
  category_id: string
  category_name: string
  group_name: string
  month: string
  actual: number
  baseline_mean: number
  z_score: number
  direction: 'high' | 'low'
  history: number[]
}

export interface AnomalyReport {
  anomalies: AnomalyItem[]
}

export interface PaydayEffectDay {
  offset: number
  avg_spend: number
}

export interface PaydayEffectReport {
  days: PaydayEffectDay[]
  baseline_daily: number
  event_count: number
}

export interface CashProjectionPoint {
  date: string
  p10: number
  p25: number
  p50: number
  p75: number
  p90: number
  deterministic: number
}

export interface CashProjectionEvent {
  date: string
  payee: string
  amount: number
  source: 'scheduled' | 'subscription'
}

export interface CashProjectionReport {
  start_balance: number
  points: CashProjectionPoint[]
  events: CashProjectionEvent[]
  goes_negative_date: string | null
}

export interface SimilarTransaction {
  id: string
  date: string
  amount: number
  payee_id: string | null
  memo: string | null
  cleared: ClearedStatus
  import_description: string | null
}

export interface SimpleFINConnection {
  id: string
  user_id: string
  last_sync_at: string | null
  sync_interval_hours: number
  sync_enabled: boolean
  daily_sync_time: string | null
  global_requests_today: number
  account_requests_today: number
  last_sync_error: string | null
  last_sync_error_at: string | null
  created_at: string
  updated_at: string
}

export interface SimpleFINRateLimitStatus {
  global_used: number
  global_remaining: number
  account_used: number
  account_remaining: number
  can_sync_global: boolean
  can_sync_account: boolean
  resets_at: string
}

export interface SyncResult {
  imported: number
  skipped: number
  matched: number
  review_queued: number
  cleared: number
  error: string | null
  global_used: number | null
  global_remaining: number | null
  account_used: number | null
  account_remaining: number | null
}

export interface TransactionMatch {
  id: string
  synced_transaction_id: string
  manual_transaction_id: string
  confidence_score: number
  status: 'pending' | 'accepted' | 'rejected'
  created_at: string
}
