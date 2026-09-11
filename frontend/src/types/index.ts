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
  /** Day of the month (1–28) before which an unmet target reads "pending"
   *  rather than "underfunded". A target may override it with its own
   *  `check_after_day`. Server: Budget.funding_day. */
  funding_day: number
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
  /** The masked display's clear part; the numbers themselves come only from
   *  GET /accounts/{id}/secrets. */
  account_number_last4?: string | null
  has_routing_number?: boolean
  simplefin_account_id: string | null
  simplefin_account_name: string | null
  simplefin_sync_enabled: boolean
  first_sync_complete: boolean
  last_simplefin_sync_at: string | null
  simplefin_balance: number | null
  balance: number
  cleared_balance: number
  uncleared_balance: number
  /** Authorised by the bank, not yet posted. Not part of
   *  balance = cleared + uncleared — pending money is in no aggregate until
   *  it posts (backend: txn_filters.PENDING_ROW). */
  pending_balance: number
  last_reconciled_at: string | null
  /** Always sent (may be null) — the balance the last reconciliation locked. */
  last_reconciled_balance: number | null
  /**
   * The day this account joined the budget. Rows dated before it are opening
   * position: nothing is auto-categorized there on first sync, and an
   * uncategorized one is not flagged as needing a category.
   *
   * A card carried in with three months of bank history is the case — that
   * spending predates the budget, so it belongs in the card's Uncovered and is
   * retired by assigning to the card, not by filling envelopes after the fact.
   *
   * Null on every account that has never been asked, which behaves exactly as
   * before the field existed. See `Account.budget_start_date` on the server.
   */
  budget_start_date: string | null
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
  is_archived: boolean
  is_system: boolean
  /** Every live category here is a card's set-aside envelope, so the grid draws
   *  no header for this group. Served, not derived — home is
   *  `GROUP_IS_CARD_ONLY` in repositories/category_filters.py, and the server's
   *  reorder rule reads the same expression.
   *
   *  The client cannot compute this: its category list filters hidden
   *  categories, so a group whose only non-card row is hidden would read as
   *  card-only here and not there. It used to compute it anyway, and the two
   *  answers disagreed — which turned group dragging off entirely. */
  is_card_only: boolean
  /** How many of this group's live categories are archived — envelopes the grid
   *  does not draw. Served, not counted here: `useCategories` asks without
   *  `include_archived`, so the client is missing the rows. Home is
   *  `GROUP_ARCHIVED_CATEGORY_COUNT` in repositories/category_filters.py.
   *
   *  A group whose count equals its drawn rows of zero is an empty header on
   *  the page and a group full of envelopes to the delete and archive
   *  endpoints. The grid says so now instead of letting the dialog be the
   *  first place anyone finds out. */
  archived_category_count: number
  /** 'wishlist' for the group the Guide keeps: rename and delete are refused,
   *  hide is not. Served from `CategoryGroup.system_key`. */
  system_key: string | null
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
  is_archived: boolean
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
  /** May money ENTER this envelope? Served, not derived — home is
   *  `repositories/category_filters.py IS_FUNDABLE`. Differs from
   *  `is_assignable` on exactly the card payment envelope, which is funded
   *  by the cards section and offered by no picker. */
  is_fundable: boolean
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
  /** The categories named outright. */
  category_ids: string[]
  /** Any category carrying one of these tags is in the filter, now and as
   *  tags change. */
  tag_ids: string[]
  /** What the filter includes right now — named categories plus every
   *  category carrying one of its tags. The grid reads THIS; the union is
   *  resolved on the server (BudgetFilterRepository.effective_category_ids)
   *  so a report handed a filter_id agrees with the budget page. */
  category_ids_effective: string[]
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
export type TargetStatus = 'funded' | 'underfunded' | 'overfunded' | 'pending'

export interface CategoryBalance {
  category_id: string
  month: string
  /** Null on a category in a system (Income) group: income is filed there,
   *  not budgeted there, so there is no envelope money to show. Served that
   *  way — see `CategoryBalance` in api/v1/schemas/category.py. */
  assigned: number | null
  activity: number
  available: number | null
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
  /** A card's set-aside envelope — the cards section owns it; the grid never
   *  draws it and its negative is not overspending. Served, not derived:
   *  see `CategoryBalance` in api/v1/schemas/category.py. */
  is_card_payment: boolean
  /**
   * How much of THIS MONTH's card inflows filed here repaid uncovered debt
   * instead of returning money to this envelope. The card owes less; no cash
   * arrived, so this envelope cannot spend it. Almost always 0.
   *
   * Already inside `available` — the adjustment is made within the carryover
   * walk, not after it — which is also why `activity` differs from the
   * register's raw sum by exactly this amount.
   *
   * Served, not derived — the client would need every month's exposure walk
   * per (category, card) to compute it. Home is `domain/cards.py`
   * (`release_split` / `card_funding`). Rendered so the adjustment is never
   * silent: money moving with nothing on screen to explain it is the defect
   * this model keeps producing.
   *
   * This month's, never a running total: the cumulative version reached ~31x
   * its first year's value on a real budget, all of it drawn as red.
   */
  repaid_uncovered_debt: number
  /**
   * How much of this row's red was spent on a card. 0 whenever `available`
   * is not negative.
   *
   * Served, not derived — home is `domain/cards.py` (`credit_floored_by_month`,
   * read out of `card_funding`'s `floored_by_category`), the same figure Ready
   * to Assign subtracts as `uncovered_current`.
   *
   * It answers whether this red costs anything, and it does not: filing a card
   * charge moves Ready to Assign by exactly zero, and at the month boundary
   * this part rides onto the card as Uncovered instead of being written off.
   * Only `available + credit_overspent` — the cash part — is ever charged.
   * So a row where this equals the whole shortfall gets the calm treatment,
   * and Cover Overspent does not offer to fund it.
   */
  credit_overspent: number
}

/** One card in the budget's cards section — see `CardStatusOut` on the
 *  server (api/v1/schemas/category.py) and domain/cards.py for the model. */
export interface CardStatus {
  account_id: string
  name: string
  /** Null only before the set-aside envelope exists (fresh migration edge). */
  category_id: string | null
  /** Ledger through the viewed month; negative = owed. */
  balance: number
  /** Cash reserved for this card; negative when payments outran the reserve. */
  set_aside: number
  /** Owed beyond the reserve. Calm and informational — a due date crossing
   *  the month boundary is a normal state, not overspending. */
  uncovered: number
  /** A settled closed card sends no row at all; a closed one with a residual
   *  balance or reserve keeps its row, tagged. Served, never derived here. */
  is_closed: boolean
  /** The part of this month's overspending riding on this card — already
   *  inside `uncovered`. It names which card carries the red, which only
   *  matters with more than one, since cards are paid separately. Attributed
   *  exactly, not apportioned: see `card_funding` in domain/cards.py. */
  overspent_this_month: number
  /** 0 when this card's reserve agrees with what it owes, otherwise the amount
   *  that does not add up. Served, not derived — home is `reserve_discrepancy`
   *  in domain/cards.py, and the integrity check reads the same field, so the
   *  page and the check cannot disagree about one card. */
  reserve_discrepancy: number
  /** The legs `set_aside` is the running total of, each through the
   *  viewed month:
   *
   *      opening + assigned + reserved − released − residual − payments
   *        === set_aside
   *
   *  Home is `CardReserve` in domain/cards.py. **Render these; never sum
   *  them.** `set_aside` is already served, and a client-side second opinion
   *  about what a reserve is made of is exactly the shape of the defect that
   *  put them here ("Two Ledgers, One Debt"). */
  assigned: number
  reserved: number
  released: number
  residual: number
  payments: number
  /** The sixth leg, first in time: YNAB's own CCP Available at an import
   *  anchor's B−1 (server home: CardStatusOut → db.models.ImportAnchor).
   *  Zero everywhere but budgets anchored at import; never derived here. */
  opening: number
  /** What is riding uncovered on this card, lifetime — distinct from
   *  `uncovered`, which is what the card OWES beyond its reserve. */
  riding: number
  /** The rest of `card_position` (domain/cards.py), beside `uncovered`.
   *
   *  **A zero `reserve_discrepancy` does not mean this card looks sensible.**
   *  That check's bounds are allowances: an over-reserve explained by
   *  assignments and a negative reserve explained by residual both report
   *  nothing, and a real budget produced one of each — a reserve several times
   *  its balance, and a reserve below zero on a card still owing thousands.
   *  Read these to say which way a card is unusual. */
  over_reserved: number
  short_reserved: number
  /** The card owes nothing and holds your money. The ONLY state "overpaid" is
   *  true of — a negative `set_aside` alone is not it, and printing the word
   *  on the sign alone is the defect these fields exist to end. */
  card_credit: number
  /** The viewed month off the card's own ledger. Every leg above is a lifetime
   *  total, so a month cannot be derived from them here.
   *  `debt_change_this_month` is signed: positive means the debt shrank. */
  charged_this_month: number
  /** EVERY credit the card's ledger took this month — refunds, rewards,
   *  somebody else paying the bill, unpaired payments — where
   *  `paid_this_month` is paired transfers from cash only. Served (home:
   *  budget_service.CardStatus ← card_month_flows); the client used to
   *  reconstruct it as `debt_change + charged − paid`, a plug that cannot
   *  fail to reconcile and so absorbed any error silently. */
  inflows_this_month: number
  paid_this_month: number
  debt_change_this_month: number
  /** Signed net of this month's rows the bank still calls pending. Served
   *  (backend/.../repositories/account_repo.py `card_month_flows`) because the
   *  client cannot see a row the money aggregates deliberately exclude.
   *  `POSTED` keeps these out of the three figures above AND out of `balance`,
   *  so the panel agrees with the balance and differs from the register by
   *  exactly this — a divergence the surface names rather than leaving as an
   *  unexplained gap between two screens. NOT added to the figures above. */
  pending_this_month: number
  /** Which months put riding debt on this card, chronological. The month is
   *  the actionable half: funding an envelope in the month it ended short
   *  retires the ride — the walk is recomputed every request, so a backdated
   *  assignment works — while funding it the month after does not reach back.
   *
   *  **Gross, where `riding` is net.** Retirement is recorded against the
   *  month of the assignment that did it, not the month that rode, so once
   *  anything has been covered there is no month attribution for what
   *  remains. `rideMonths` names the difference rather than implying every
   *  month here is still owed. */
  rode_by_month: RodeMonth[]
  /** `overspent_this_month` broken out by the envelope that rode onto this
   *  card, largest first. Home: `CardFunding.floored_by_pair` (backend
   *  domain/cards.py) — the client cannot derive it, since the allocation is
   *  a running walk per (category, card). Sums to `overspent_this_month`. */
  overspent_by_category: RodeCategory[]
}

/** One month that put riding debt on a card. */
export interface RodeMonth {
  month: string
  amount: number
}

/** One envelope that rode onto a card in the viewed month. */
export interface RodeCategory {
  category_id: string
  /** Named server-side: a hidden or archived envelope can ride, and the
   *  client's category list does not always carry it. */
  category_name: string
  amount: number
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
  /** `total_overspent` split by what funded it. The headline stays whole — the
   *  red on the grid is real either way — but only `total_overspent_cash` can
   *  ever charge Ready to Assign, so every call to action reads that one.
   *  `total_overspent_credit` rolls onto its card at the month boundary and
   *  needs no action at all. See `domain/cards.py`. */
  total_overspent_cash: number
  total_overspent_credit: number
  /** How many categories carry a cash shortfall — what Cover Overspent lists.
   *  At most `overspent_count`. */
  overspent_count_cash: number
  /** Committed to months after this one; already deducted from to_be_assigned */
  assigned_in_future: number
  /** B, the first month this budget's envelope math re-derives — set only on
   *  budgets anchored at import (server home: BudgetMonthResponse →
   *  db.models.ImportAnchor). Null on every other budget. Month navigation
   *  clamps here; months before it live in the register and reports only —
   *  never request or derive a pre-anchor budget month. */
  anchor_month: string | null
  category_balances: CategoryBalance[]
  /** The budget's cards — empty when it has none. The cards section draws
   *  exactly this and computes nothing. */
  cards: CardStatus[]
}

export interface BudgetTransactionsResponse {
  transactions: Transaction[]
  total_count: number
  /** Totals cover the full filter match, not just the page */
  total_amount: number
  /** Transaction id → the account's balance as of that row. Present only when
   *  `running_balance` was asked for on a single-account listing; `{}`
   *  otherwise. A pending row has no entry — it has not moved the balance, and
   *  a zero would read as one that had. Served rather than accumulated here:
   *  the server owns the row order, and a running total in a different order
   *  is nonsense that reads as arithmetic. */
  running_balances: Record<string, number>
}

export interface Transaction {
  id: string
  budget_id: string
  account_id: string
  date: string
  /** The user's originally-entered date when bank data overwrote `date` */
  entered_date: string | null
  /** The amount this row had before the bank's posted amount replaced it —
   *  a hold posting as a larger charge, or an accepted amount-change review.
   *  Null when the bank never changed it. Provenance for the bank tooltip;
   *  never money. Home: `Transaction.entered_amount` (backend models.py). */
  entered_amount: number | null
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
   * What this row was filed in before that category was deleted. Provenance,
   * in the spirit of `entered_date` and `bank_payee` — set by
   * `CategoryService` (backend/src/igab/services/category_service.py).
   *
   * DISPLAY ONLY. Never treat it as a category: this row is uncategorized,
   * and `needs_category` below is the field that says so. Anything that
   * counts, filters or groups by `prior_category_id` rebuilds the exact bug
   * these columns replaced.
   */
  prior_category_id: string | null
  prior_category_name: string | null
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
  /** Where the row came from: 'manual' | 'import' | 'sync' | 'scheduled' |
   *  'ai_receipt' | 'ai_nl'; null = unknown (rows older than the stamp).
   *  Home: `Transaction.created_via` (backend models.py). Presentation only —
   *  it is what lets a row the bank matched say it was entered by you. */
  created_via: string | null
  /** The schedule this row was entered from, or null. Home:
   *  `Transaction.scheduled_transaction_id`. */
  scheduled_transaction_id: string | null
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
  /** Raw bank names that map to this payee. A list — a bank name may itself
   *  contain a comma. */
  mapping_samples: string[]
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
  /** An existing line to update in place (PUT …/splits); omit for a new one. */
  id?: string
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
  /** A saved filter was named and could not be found — backend
   *  `CategoryScope` in `report_scope.py` says what the scope then holds. */
  filter_unavailable: boolean
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
  /** monthly_funding | weekly_funding | savings_balance — see TargetType in
   *  backend/src/igab/domain/enums.py. */
  target_type: string
  target_amount: number
  /** Savings balance only: paces the shortfall over the months left. */
  target_date: string | null
  /** Overrides the budget's funding_day for this target (1–28). */
  check_after_day: number | null
  /** Weekly funding only: 0=Monday … 6=Sunday. */
  weekday: number | null
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
  last_created_date: string | null
  /** Twice-monthly only: the other day of the month (the first is the start
   *  date's day). */
  second_day_of_month: number | null
  transfer_account_id: string | null
  /** Non-null on a schedule an import created (a future-dated YNAB row). */
  import_id: string | null
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
  'last_month_assigned' | 'last_month_spent' | 'average_assigned' | 'average_spent' | 'reset'

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
  net_worth: number
  net_worth_prev: number
  burn_rate_30: number
  burn_rate_90: number
  /** Monthly essential spending over the Guide's 90-day window — the number
   *  the roadmap's emergency-fund target is built from. null until something
   *  is tagged Essential (untagged it would equal burn rate). Server-computed:
   *  TransactionRepository.essential_spend. */
  essentials_monthly: number | null
  essentials_tagged: boolean
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
  /** Stated asset values — in total_assets and the net line without
   *  appearing in any account series; the charts footnote the gap. */
  asset_value_total: number
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
  asset_value_total: number
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
  /** Owed on accounts closed with a balance still on them, excluded from
   *  `total_balance`. Net worth counts it, so the page says so rather than
   *  letting two figures labelled Total Liabilities disagree in silence. */
  closed_with_balance_count: number
  closed_with_balance_total: number
}

export interface AccountCompositionPoint {
  date: string
  // Balance per account-type key present in the budget (custom types included)
  balances: Record<string, number>
  /** Net worth at this point — served (report_service.account_composition)
   *  rather than summed from `balances`, because unmanaged debts and stated
   *  asset values sit in net worth without appearing in any account series. */
  net_worth: number
  /** The stated-asset share of the gap between the net line and the visible
   *  stack — footnoted when non-zero. */
  asset_value_total: number
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
  /** Spent-mode category nodes: the activity classes the node counted, which
   *  its drill-down must list. The Savings, Debt Payments and Uncategorized
   *  pseudo-nodes differ by nothing else. */
  activity_classes?: string[] | null
}

export interface SankeyLink {
  source: string
  /** A node name, not money — Sankey links are named endpoints. */
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
  /** null in budgeted mode, which draws from assignments and has no activity
   *  class to split by — "not claimed", never zero. */
  total_spending: number | string | null
  total_savings: number | string | null
  total_debt_principal: number | string | null
  category_payees: Record<string, CategoryPayee[]>
  group_categories: Record<string, CategoryPayee[]>
}

export interface BudgetActualItem {
  category_id: string
  category_name: string
  category_group_name: string
  assigned: number
  spent: number
  /** Against the plan floored at zero — backend `domain/plan.py`. */
  variance: number
  variance_pct: number
  /** The server's verdict, same rule as Plan vs Reality. Never re-derive it
   * from `spent > assigned`: a drained envelope has a negative assignment. */
  overspent: boolean
}

export interface BudgetActualReport {
  categories: BudgetActualItem[]
  total_assigned: number
  total_spent: number
  /** A saved filter was named and could not be found — backend
   *  `CategoryScope` in `report_scope.py` says what the scope then holds. */
  filter_unavailable: boolean
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
  /** Which reading the figures are — served, see `VolatilityResponse` and
   *  `domain.amortize.spread_forward`. The caption and the export read it. */
  amortized: boolean
  /** The complete months the statistics read (server-decided). Drill with
   *  these — a window computed here drifted from the backend's once already. */
  window_start: string
  window_end: string
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

/** Carried by every report scoped by a saved filter. */
export interface SavedFilterScope {
  /** A saved filter was named and could not be found — deleted in another tab,
   *  or belonging to another budget. Its own share of the scope then matches
   *  nothing; the report is NOT unfiltered. Nor is it necessarily empty: the
   *  scope is the union of the categories, the tags and the filter, so a
   *  category picked beside the lost filter still draws. `ReportNotes` says
   *  so on every chart that reads one of these. */
  filter_unavailable: boolean
}

export interface SpendingGroupedReport extends SavedFilterScope {
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

/** What a lean month costs — GET /reports/essentials. `essentials_90d` is the
 *  Guide's figure and the Overview card's; the table averages complete months. */
/** One month of the emergency-fund coverage report. */
export interface CoveragePoint {
  month: string
  fund_balance: number
  /** Trailing three-month average of essential spending — the Guide's 90-day
   *  window said in months, so this line and the roadmap's target cannot tell
   *  different stories about the same household. */
  essentials: number
  /** Null, never zero, for a month with no essential spending to divide by. */
  coverage_months: number | null
  /** The band AT THIS MONTH. It moves: as spending grows the target grows
   *  with it, and a fund standing still loses coverage without losing a cent. */
  target_low: number
  target_high: number
  /** A self-reported balance is carried flat from the date it was given. */
  external_counted: boolean
}

export interface EmergencyCoverageReport {
  months: number
  tagged: boolean
  fund_balance: number | null
  fund_source: string | null
  /** The Essentials report's own runway, quoted rather than recomputed. */
  coverage_months: number | null
  essentials_monthly: number
  target_low: number
  target_high: number
  target_range: [number, number]
  series: CoveragePoint[]
  external_amount: number | null
  external_as_of: string | null
  current_month: string
}

export interface EssentialsReport {
  tagged: boolean
  months: number
  window_start: string
  window_end: string
  essentials_90d: number
  monthly_total_average: number
  categories: {
    category_id: string | null
    name: string
    group_name: string | null
    total: number
    monthly_average: number
    months_with_spend: number
  }[]
  monthly_series: { month: string; total: number }[]
  reserve: { months: number; amount: number }[]
  roadmap_range: [number, number]
  /** What the Guide reads as the emergency fund today, and how many lean
   *  months it covers. Null when nothing looks like a fund. */
  emergency_fund_balance: number | null
  emergency_fund_source: string | null
  runway_months: number | null
  /** Tagged Essential and still not counted, by class — see
   *  `CostOfLivingReport.class_excluded`. */
  class_excluded: SpendingClassExcluded[]
}

export interface SpendingTrendSeries {
  id: string
  name: string
  group_id: string | null
  group_name: string | null
  monthly: number[]
  total: number
}

export interface SpendingTrendsReport extends SavedFilterScope {
  months: string[]
  series: SpendingTrendSeries[]
  monthly_totals: number[]
  total: number
  class_excluded: { activity_class: string; label: string; categories: number; total: number }[]
}

export interface IncomeSource {
  payee_id: string | null
  payee_name: string
  monthly: number[]
  total: number
  count: number
}

export interface IncomeBySourceReport {
  months: string[]
  sources: IncomeSource[]
  monthly_totals: number[]
  total: number
  /** `total` over the complete months the window holds, served — Cost of
   *  Living's Take-home quotes the same figure. Never divide here. */
  avg_monthly: number
  months_averaged: number
}

export interface CategoryHistoryReport {
  category_id: string
  category_name: string
  months: {
    month: string
    assigned: number
    activity: number
    /** Null for an income category: "Income categories do not hold money", so
     *  their available is a lifetime carryover the budget page never draws.
     *  Their monthly activity is meaningful and is still served. */
    available: number | null
  }[]
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
  /** The largest by spend — a ranking, never a page. */
  payees: PayeeSpending[]
  /** Over EVERY payee in the window, not over `payees`. Each row's `pct` is a
   *  share of this. */
  total: number
  /** How many payees spent in the window. Served because a client that knows
   *  only "25 rows" cannot say whether that is all of them — the Total Payees
   *  card used to report the ranking cap. */
  payee_count: number
  /** How many of the largest payees make up 80% of `total`, counted over
   *  every payee — the Pareto card's figure, which the top 25 cannot give
   *  (backend `domain/concentration.py`). null when nothing was spent. */
  payees_to_80pct: number | null
}

export interface DayPatternItem {
  day_of_week: number
  day_name: string
  total: number
  count: number
  avg_transaction: number
}

export interface DayPatternsReport extends SavedFilterScope {
  days: DayPatternItem[]
  /** Savings / debt activity in the categories the user selected that this
   *  chart will not count. Empty without a selection. */
  class_excluded: SpendingClassExcluded[]
  /** The activity classes these figures count, passed to the drill-down so a
   *  bar and the panel it opens total the same. */
  counted_classes: string[]
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
  /** Null for a split whose legs do not agree on one class: the parent
   *  carries no category, so there is no honest single answer and
   *  `activity_label` reads "Split". */
  activity_class: string | null
  /** Its display label, served rather than mirrored — a local copy here had
   *  already drifted from the backend's wording. */
  activity_label: string
}

export interface TimelineReport extends SavedFilterScope {
  transactions: TimelineTransaction[]
}

/** The figures a recurring line carries — same shape for a category and for
 *  a payee inside it, because the arithmetic is the same. */
export interface RecurringSpend {
  monthly_amounts: number[]
  /** True monthly burden: total / months since the first charge. Per payee
   *  that is a service's cost; per category it is the envelope's burn rate. */
  avg_monthly: number
  total: number
  /** Typical charge: total / charge count */
  avg_per_charge: number
  last_charge_date: string | null
  transaction_count: number
}

export interface SubscriptionPayee extends RecurringSpend {
  payee_id: string | null
  payee_name: string
}

export interface SubscriptionCategory extends RecurringSpend {
  category_id: string
  category_name: string
  group_name: string
  payees: SubscriptionPayee[]
}

export interface SubscriptionsSummary {
  total_monthly: number
  total_annual: number
  active_count: number
}

export interface SubscriptionsReport {
  /** The complete months the window holds — every entry of `months`, on
   *  every day (backend `domain.dates.complete_month_window`). The MOST an
   *  effective-monthly figure divides by: each line divides by the months
   *  since its own first charge. 0 when nothing was charged in the window. */
  months_averaged: number
  subscriptions: SubscriptionCategory[]
  summary: SubscriptionsSummary
  months: string[]
}

export interface SavingsCategory {
  category_id: string
  category_name: string
  group_name: string
  /** Available at each month's end, from the Budget page's own walk
   *  (BudgetService.envelope_series). `null` where no figure can be stated —
   *  before an import the history cannot reproduce; see
   *  `SavingsReport.unrecovered`. Absent, not zero: draw a gap. */
  monthly_balances: (number | null)[]
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

export interface ReportDrainMove {
  move_id: string
  month: string
  date: string
  amount: number
  from_category_id: string
  from_name: string
  to_category_id: string | null
  to_name: string
}

/** Money moved out of the report's envelopes in its window — the audit
 *  trail, named on both sides. Shaped by backend domain/drains.py. */
export interface ReportDrains {
  total: number
  moves: ReportDrainMove[]
}

/** An envelope whose balance before an import could not be walked back from
 *  YNAB's figure, so its line starts at `starts_from`. */
export interface SavingsUnrecovered {
  category_id: string
  category_name: string
  starts_from: string
}

export interface SavingsReport {
  categories: SavingsCategory[]
  summary: SavingsSummary
  months: string[]
  drains: ReportDrains
  unrecovered: SavingsUnrecovered[]
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
  /** null when the payday windows cover every day, so there is no "outside"
   *  to average — backend PaydayEffectResponse. Never read it as 0.00: that
   *  says the household spends nothing between paydays. */
  baseline_daily: number | null
  event_count: number
  /** The smallest inflow the server counted as a payday — backend
   *  PAYDAY_FLOOR, served so the info panel quotes the rule it applied. */
  payday_floor: number
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
  sync_enabled: boolean
  /** UTC hours (0-23) this connection syncs itself at; [] is never. The
   *  server owns the schedule — see db/models.SimpleFINConnection.sync_hours
   *  — and validates the count against its own daily rate limit. */
  sync_hours: number[]
  global_requests_today: number
  account_requests_today: number
  last_sync_error: string | null
  last_sync_error_at: string | null
  created_at: string
  updated_at: string
}

/**
 * Served by GET /simplefin/config. The client cannot decide any of this: the
 * encryption key is server-side env, so the server is the only one that knows
 * whether bank sync can store credentials at all.
 * Home: backend/src/igab/integrations/simplefin/encryption.py
 */
export interface SimpleFINConfig {
  configured: boolean
  /** Null when configured; otherwise what is wrong, in the user's words. */
  problem: string | null
  /** The one command that produces an acceptable key — served, not duplicated here. */
  generate_key_command: string
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

export interface CostOfLivingGroup {
  group_name: string
  monthly_amounts: number[]
  total: number
  avg_monthly: number
  /** Share of the cost-of-living total, 0–100 — not of income, so shares add
   *  to 100. */
  share: number
  /** The categories behind this bar, for the drill-down. Empty on the
   *  Uncategorized bucket, which drills by "no category" instead — an empty
   *  id list filters nothing and would list the whole budget. */
  category_ids: string[]
}

export interface CostOfLivingReport {
  months: string[]
  /** How many months the `avg_monthly_*` figures divide by: every entry of
   *  `months`, all of them complete, on every day (backend
   *  `domain.dates.complete_month_window`). Served rather than derived from
   *  `months.length`, so the page never divides for itself. */
  months_averaged: number
  /** The window the figures cover. Served, not re-derived: "twelve months
   *  back from the first of that month, to today" is the report's rule and
   *  belongs on one side of the wire. */
  window_start: string
  window_end: string
  groups: CostOfLivingGroup[]
  /** The wide tier: everything non-discretionary. */
  avg_monthly_cost_of_living: number
  /** The lean tier, over the SAME window — which is what makes the difference
   *  between them a real figure rather than a calendar artifact. Null when
   *  nothing is tagged Essential (backend `basis_is_chosen`): all spending is
   *  not what a household could not cut. */
  avg_monthly_essentials: number | null
  /** Cost of living less essentials: what a lean month could shed. Null
   *  whenever essentials is. */
  avg_monthly_non_essential: number | null
  avg_monthly_income: number
  /** Share of take-home spoken for, against the WIDE tier. Null when there is
   *  no income on record: unknown, not 100%. */
  required_ratio: number | null
  /** The lean tier against take-home. Above 100 the household cannot cover
   *  what it could not cut. */
  essentials_ratio: number | null
  basis: 'bound' | 'tag' | 'all'
  /** False when no category is tagged Essential or Cost of living (basis
   *  'all'): the figures then cover every category — the burn rate. */
  tagged: boolean
  /** Tagged Essential and still not counted, by class. Tagging a category is
   *  pointing at it, so absence without this reads as a bug — which is
   *  exactly how "I tagged ten and two showed up" was reported. */
  class_excluded: SpendingClassExcluded[]
  /** The activity classes these figures count, passed to the drill-down so a
   *  bar and the panel it opens total the same. */
  counted_classes: string[]
  /** The necessity tier the groups roll up. Membership is per row (debt
   *  principal joins by class), so the drill sends it too. */
  necessity_tier: string
}

export interface WishlistDisciplineReport {
  cooled_then_bought: number
  cooled_then_dropped: number
  bought_early: number
  /** Dropped before the cooling-off period ended — resisted money, but not
   *  something the cooling-off period did. */
  dropped_early: number
  still_open: number
  /** Every dropped wish's cost, waited on or not. */
  resisted_total: number
  /** How many wishes `resisted_total` sums — the card's count. */
  resisted_count: number
  bought_total: number
  open_total: number
  avg_days_to_buy: number | null
  avg_wish_cost: number | null
  unplaced: number
}
