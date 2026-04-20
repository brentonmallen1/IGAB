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
  is_closed: boolean
  sort_order: number
  note: string | null
  simplefin_account_id: string | null
  balance: number
  cleared_balance: number
  uncleared_balance: number
  last_reconciled_at: string | null
  uncategorized_count: number
}

export type AccountType = 'checking' | 'savings' | 'credit_card' | 'loan' | 'tracking'

export interface CategoryGroup {
  id: string
  budget_id: string
  name: string
  sort_order: number
  is_hidden: boolean
  is_system: boolean
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
  category_balances: CategoryBalance[]
}

export interface Transaction {
  id: string
  budget_id: string
  account_id: string
  date: string
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
  created_at: string
  updated_at: string
}

export type ClearedStatus = 'pending' | 'uncleared' | 'cleared' | 'reconciled'

export interface Payee {
  id: string
  budget_id: string
  name: string
  default_category_id: string | null
  transfer_account_id: string | null
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

export interface SimpleFINConnection {
  id: string
  user_id: string
  last_sync_at: string | null
  sync_interval_hours: number
  requests_today: number
  created_at: string
  updated_at: string
}
