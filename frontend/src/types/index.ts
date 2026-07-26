export interface User {
  id: string
  email: string
  display_name: string | null
}

export interface Budget {
  id: string
  name: string
  currency_code: string
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
  uncategorized_count: number
}

export type AccountType = 'checking' | 'savings' | 'credit_card' | 'loan' | 'tracking'
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
  sort_order: number
  note: string | null
  is_hidden: boolean
  linked_account_id: string | null
  tags?: TagSimple[]
}

export interface BudgetView {
  id: string
  budget_id: string
  name: string
  sort_order: number
  category_ids: string[]
  created_at: string
  updated_at: string
}

export interface CategoryBalance {
  category_id: string
  month: string
  assigned: number
  activity: number
  available: number
}

export interface BudgetMonth {
  month: string
  to_be_assigned: number
  total_assigned: number
  total_activity: number
  total_overspent: number
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
  amount: number
  payee_id: string | null
  category_id: string | null
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
  has_sync_source: boolean
  linked_transaction_id: string | null
  link_confidence: number | null
  created_at: string
  updated_at: string
}

export type ClearedStatus = 'pending' | 'uncleared' | 'cleared' | 'reconciled'

/** Per-item outcome of a bulk transaction action */
export interface BulkActionResult {
  updated: string[]
  failed: Array<{ id: string; reason: string }>
}

export interface Payee {
  id: string
  budget_id: string
  name: string
  default_category_id: string | null
  transfer_account_id: string | null
  mapping_samples: string | null
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
  expenses: number
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
  | 'reset_available'
  | 'reset_assigned'

// ─── Report Types ───────────────────────────────────────────────────────────

export interface DashboardMetrics {
  to_be_assigned: number
  net_worth: number
  net_worth_prev: number
  burn_rate_30: number
  burn_rate_90: number
  savings_rate: number
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
  accounts: { account_id: string; account_name: string; account_type: string; balance: number }[]
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
  interest_rate: number
  baseline_payoff_date: string | null
  live_payoff_date: string | null
  total_interest_remaining: number
  never_pays_off: boolean
}

export interface LiabilitiesBalancePoint {
  date: string
  per_liability: Record<string, number>
  total: number
}

export interface LiabilitiesReport {
  items: LiabilitiesReportItem[]
  total_balance: number
  total_interest_remaining: number
  balance_over_time: LiabilitiesBalancePoint[]
}

export interface AccountCompositionPoint {
  date: string
  checking: number
  savings: number
  credit_card: number
  loan: number
  tracking: number
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
  total_expense: number
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

export interface SpendingGroupedReport {
  groups: SpendingGroupItem[]
  total: number
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
}

export interface TimelineTransaction {
  id: string
  date: string
  amount: number
  payee_name: string | null
  category_name: string | null
  memo: string | null
}

export interface TimelineReport {
  transactions: TimelineTransaction[]
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
