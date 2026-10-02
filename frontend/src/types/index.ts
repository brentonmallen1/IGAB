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
  /** Whether transfers with this account count as saving — read only for an
   *  off-budget asset (`utils/accountKinds.isTrackedAsset`). Served from the
   *  column; the rule is `domain/activity_class.py` rules 5 and 7. */
  counts_as_savings: boolean
  /** The stored emergency-fund mark. Whether the balance is counted is
   *  decided on the server — home is `repositories/txn_filters.py
   *  EMERGENCY_FUND_ACCOUNT`, which also requires an off-budget savings
   *  account; the server refuses the flag on any other shape. */
  counts_toward_emergency_fund: boolean
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
  /** When the bank computed `simplefin_balance` — the bridge's own
   *  `balance-date`, not when we fetched it. Null before the column existed
   *  or when the bridge omitted it. */
  simplefin_balance_date: string | null
  /** `simplefin_balance - cleared_balance`, signed; null when the bank has
   *  reported nothing. Served (backend: domain/bank_balance.py) — the sync
   *  decides on the same rule whether a run is degraded. */
  bank_drift: number | null
  /** Why the two figures differ: 'agree' | 'in_review' | 'unposted' |
   *  'stale' | 'unexplained'. Only 'unexplained' means rows may be missing;
   *  the page used to tell the user to refetch 90 days for all of them.
   *  (backend: domain/bank_balance.py) */
  bank_drift_reason: 'agree' | 'in_review' | 'unposted' | 'stale' | 'unexplained' | null
  /** The part of `bank_drift` that `bank_unposted_cleared` and
   *  `bank_in_review` do not account for, signed.
   *  (backend: domain/bank_balance.py) */
  bank_drift_unexplained: number | null
  /** Cleared money the bank has not posted against — the ledger running
   *  ahead of the feed. (backend: txn_filters.CLEARED_AHEAD_OF_BANK) */
  bank_unposted_cleared: number | null
  /** Cleared money a pending review holds beside the bank's own copy — the
   *  ledger counting a row twice until the review queue is answered.
   *  (backend: txn_filters.IN_REVIEW_CLEARED) */
  bank_in_review: number | null
  /** Whether the sync calls this gap a fault. Served, not re-derived here:
   *  the sync decides it and the page must not be free to disagree with the
   *  sync badge. (backend: domain/bank_balance.drift_is_a_fault) */
  bank_drift_is_fault: boolean
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
   * spending predates the budget, so it belongs in the card's debt not covered and is
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
  /** Every live category here is a card's envelope, so the grid draws
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

/** `Category.savings_mode` — see `category_filters.SavingsMode`. */
export type SavingsMode = 'sent_out' | 'kept_here'
/** `Category.savings_role` — see `category_filters.SavingsRole`. */
export type SavingsRole = 'none' | SavingsMode

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
   *  `is_assignable` on exactly the card's envelope, which is funded
   *  by the cards section and offered by no picker. */
  is_fundable: boolean
  is_categorizable: boolean
  /** The stored choice only; null when the tags decide. Read `savings_role`
   *  for the answer. */
  savings_mode: SavingsMode | null
  /** How this category's money counts as saved. Served, not derived — home is
   *  `repositories/category_filters.py SAVINGS_ROLE`: it reads the Savings and
   *  Emergency fund tags and the default each implies. */
  savings_role: SavingsRole
  /** Drawn in the Credit cards section rather than the grid: a card's own
   *  envelope, or the budget's Interest & fees envelope. Served, not derived —
   *  home is `repositories/category_filters.py CARD_SECTION_CATEGORY`, which the
   *  server's group header and reorder rules read too. */
  in_card_section: boolean
  /** Kept by the app (Interest & fees): the server refuses to rename, archive,
   *  delete or move it, so the UI does not offer them. Served, not derived —
   *  home is `Category.is_protected` and `CategoryService.require_unlocked`. */
  is_protected: boolean
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
  /** What Auto-Assign's "Target Amount" would set assigned to — the figure on
   *  the inspector's button. Served (TargetService.target_assigned, the rule
   *  the apply runs); `null` when there is no target. */
  target_assigned: number | null
  /** A card's envelope — the cards section owns it and the grid never
   *  draws it. Below zero it is overspent like any envelope, and Cover
   *  Overspent covers it by assigning to the card. Served, not derived:
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
   * this part rides onto the card as debt not covered instead of being written off.
   * Only `available + credit_overspent` — the cash part — is ever charged.
   * So a row where this equals the whole shortfall gets the calm treatment,
   * and Cover Overspent does not offer to fund it.
   */
  credit_overspent: number
}

/** One card in the budget's cards section — see `CardStatusOut` on the
 *  server (api/v1/schemas/category.py) and domain/cards.py for the model. */
/** The situation a card's Set aside is in (backend `domain/cards.py`
 *  `SetAsideState`). Below zero is always "overspent" on the card's line;
 *  these name the cause, because the causes want different remedies. */
export type SetAsideState =
  | 'funded'
  | 'surplus'
  | 'card_holds_it'
  | 'settled_by_others'
  | 'refund_outran_envelope'
  | 'settled_elsewhere'
  | 'ride_unfunded'
  | 'paid_ahead'
  /** More than one cause below zero and none explains all of it. The row
   *  names what is present and attributes nothing — the reserve identity is
   *  bounds, not parts, so any split would be a guess. */
  | 'mixed'
  /** Money was moved out of the envelope past what it held — a release or a
   *  negative assignment. No payment happened; the money is in Ready to
   *  Assign. Assign to put it back. */
  | 'moved_out'

export interface CardStatus {
  account_id: string
  name: string
  /** Null only before the card's envelope exists (fresh migration edge). */
  category_id: string | null
  /** Ledger through the viewed month; negative = owed. */
  balance: number
  /** Cash reserved for this card. Negative is overspent: covered from Ready to
   *  Assign on the 1st unless assigned before then. */
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
  /** YNAB's own CCP Available at an import anchor's B−1 (server home:
   *  CardStatusOut → db.models.ImportAnchor). Zero everywhere but budgets
   *  anchored at import; never derived here. */
  opening: number
  /** What Ready to Assign absorbed, lifetime, each time a month ended with
   *  this card's Set aside below zero — overspending on the card, written off
   *  on the 1st like any envelope's. Served (CardStatusOut); never derived. */
  written_off: number
  /** This month's part of `written_off`: last month's overspending on this
   *  card, absorbed by this month's Ready to Assign. */
  written_off_this_month: number
  /** What is riding uncovered on this card, lifetime — distinct from
   *  `uncovered`, which is what the card OWES beyond its reserve. */
  riding: number
  /** Uncovered debt the budget arrived with (an import's opening position),
   *  less what assignments to the card have retired of it. Not `riding`: no
   *  month of this budget ended short to put it there, so "fund that month's
   *  envelope" cannot reach it — only assigning to the card does. */
  imported_riding: number
  /** What assignments to this card have retired of its ride, lifetime.
   *  Served; never reconstruct it as `gross rides − riding`. */
  covered: number
  /** This month's residual — the figure `set_aside_state` was decided on. A
   *  negative Set aside is always this month's (last month's was written
   *  off), so quote this, never lifetime `residual`. */
  residual_this_month: number
  /** The part of this month's residual that came back through a receivable
   *  ledger — somebody settling up. Quote this for a settle-up. */
  residual_from_ledgers_this_month: number
  /** Does funding the month an envelope ended short retire THIS card's ride?
   *  False when the shortfall is shared with another card, which funds
   *  first. Key every "fund the month and it disappears" sentence on this. */
  ride_reaches_this_card: boolean
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
  /** Which situation this card's Set aside is in. Served, and
   *  NOT derivable here: `settled_by_others` and `refund_outran_envelope`
   *  are told apart only by `residual_by_pair` and by whether an envelope was
   *  ever assigned to, and `settled_elsewhere` needs `floored_by_pair` —
   *  none of which crosses the wire. Home: backend `domain/cards.py`
   *  `SetAsideState`; `cardRow.ts` maps it to copy and must not branch on a
   *  cause of its own. */
  set_aside_state: SetAsideState
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
  /** What this month's Ready to Assign absorbed on the 1st: last month's
   *  overspending, less what rode onto cards, per envelope (card envelopes
   *  included), largest first. Served (BudgetMonthResponse) — the header
   *  names it and never computes it. */
  overspent_last_month: { category_id: string; amount: number }[]
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
  /** Who this row was paid to: payee_id, or for a split leg (which has none)
   *  its parent's. Server-computed — PAYEE_OF_RECORD_ID in backend
   *  txn_filters.py — because a list of legs does not carry their parents.
   *  Display only (render via utils/transferDisplay.ts); edit payee_id. */
  payee_of_record_id: string | null
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
  /** null on the Uncategorized line — backend `domain/spending.py`. */
  id: string | null
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
  /** The running month: its figures are month-to-date. Drawn apart and
   *  labelled "so far" (`utils/reportMonths.ts`), never in an average, total
   *  or headline. Home: backend `domain.dates.ReportWindow`. */
  partial_month: boolean
  income: number
  /** Money spent. Saving and debt principal are separate — both leave the
   *  budget, but neither is spending. */
  expenses: number
  /** Saved: `savings_moved + savings_held` (backend `domain/savings.py`). */
  savings: number
  savings_moved: number
  savings_held: number
  debt_principal: number
  /** income - expenses - savings_moved - debt_principal: money that left the
   *  accounts. Held money never left them, so `net` does not subtract it
   *  (backend `ReportService.income_vs_expense`). */
  net: number
}

export interface IncomeExpenseReport {
  months: IncomeExpenseMonth[]
  /** The classes `expenses` counts — what the Expenses drill-down lists. */
  expense_classes: string[]
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
  | 'last_month_assigned'
  | 'last_month_spent'
  | 'average_assigned'
  | 'average_spent'
  | 'reset'
  | 'target_amount'

/** Bulk strategies offered by the TBA hero's Assign dropdown */
export type AssignStrategy =
  | 'underfunded'
  | 'target_amount'
  | 'last_month_assigned'
  | 'last_month_spent'
  | 'average_assigned'
  | 'average_spent'
  | 'reduce_overfunded'
  | 'reset_available'
  | 'reset_assigned'

// ─── Report Types ───────────────────────────────────────────────────────────

/** What a lean month costs, both ways — served by the dashboard, the
 *  Essentials and Emergency Fund reports, the Guide's essential-expenses signal
 *  and the sizer. Home: `guide/concepts.py::essentials_monthly`, read through
 *  `services/essentials.py`. `as_paid` is the last three complete months as bills landed;
 *  `spread` swaps Long-term expense bills for a twelfth of the year's;
 *  `spread_on` is the budget's setting and `monthly` the one it selects. */
export interface EssentialsFigures {
  as_paid: number
  spread: number
  spread_on: boolean
  monthly: number
  /** The complete months `as_paid` averages — the last three, or fewer on a
   *  young budget; null before any history. Said wherever the figure is. */
  window_start: string | null
  window_end: string | null
}

/** GET/PUT /reports/settings — `services/report_settings.py`. */
export interface ReportSettings {
  spread_sinking_funds: boolean
}

/** What a month costs, for a runway (backend `domain/runway.py`
 *  `SpendingBasis`): all spending, the Cost of Living tier, or Essentials —
 *  each the three complete months the Essentials headline averages. */
export type RunwaySpending = 'all' | 'cost_of_living' | 'essentials'

/** What money a runway spends (backend `MoneyBasis`): the budget's cash, plus
 *  what the emergency fund holds outside it, plus every off-budget savings
 *  account — or, on the Emergency Fund report, the fund alone. */
export type RunwayMoney = 'checking' | 'with_fund' | 'with_savings' | 'fund'

/** How long the money lasts if income stopped, at one choice — the one runway
 *  rule, server-computed (`domain/runway.py`). Every surface that quotes a
 *  runway reads this shape, so each can say what it read. */
export interface RunwayFigure {
  spending: RunwaySpending
  money: RunwayMoney
  /** null when nothing is tagged into the tier: unknown, not zero. */
  monthly_spending: number | null
  /** The money counted, on-budget card debt already subtracted; null when it
   *  would count an emergency fund nobody has chosen. */
  money_total: number | null
  /** What was subtracted for the cards (owed, positive). */
  card_debt: number
  /** One decimal. null when nothing is being spent; 0 when the money is
   *  already gone. */
  months: number | null
  /** The reader's today plus `months`. */
  runs_out_on: string | null
}

/** The Overview's Runway card: Essentials against the cash and the emergency
 *  fund, falling back (and saying why) when either is missing. */
export interface OverviewRunway extends RunwayFigure {
  fund_chosen: boolean
  essentials_known: boolean
  window_start: string | null
  window_end: string | null
}

export interface DashboardMetrics {
  net_worth: number
  net_worth_prev: number
  /** What began being counted between `net_worth_prev`'s day and today —
   *  accounts arriving with their opening balances, values first stated —
   *  and the change less it: the card's figure. Server-computed:
   *  `domain/tracking_start.py`. */
  net_worth_entered: number
  net_worth_change: number
  /** Net spending over the last 30 days, and over the 60 days before them
   *  per 30 days — no day in both. Server-computed: `domain/burn_rate.py`;
   *  the change between them is composed in `charts/burnRateView.ts`. */
  burn_rate_30: number
  burn_rate_prior_60: number
  /** What a lean month costs, both ways — the figures the roadmap's
   *  emergency-fund target is built from. null until something is tagged
   *  Essential (untagged it would equal burn rate). Server-computed:
   *  `services/essentials.py`. */
  essentials: EssentialsFigures | null
  essentials_tagged: boolean
  /** null when no income was recorded in the window — a gap, not a floor.
   *  "No income" and "saved nothing" are different facts. */
  savings_rate: number | null
  /** How long the money lasts if income stopped (backend
   *  `services/runway.py`). */
  runway: OverviewRunway
  income_this_month: number
  expenses_this_month: number
  /** Spending over the equal-length window before this one
   *  (`domain.dates.previous_window`). */
  expenses_prev_month: number
  /** Principal paid into tracked debts over the window. */
  debt_payments_this_month: number
  /** What living cost over the window: every class in the server's
   *  COST_OF_LIVING_CLASSES — spending plus debt payments, never savings.
   *  Read against income by `components/reports/livingMeans.ts`. */
  outflows_this_month: number
  /** `id` is null on the Uncategorized line. */
  top_categories: { id: string | null; name: string; group_name: string; total: number }[]
  /** The last 12 complete months, oldest first, whatever the requested window
   *  — fewer on a younger budget, none on an empty one; a quiet month inside
   *  the window is zeros. Served by `report_basics.means_months` with the
   *  composition `outflows_this_month` uses; read by `livingMeans.meansTrend`. */
  means_months: MeansMonth[]
}

/** One complete month of the Overview's Means trend. `income` is the INCOME
 *  class and `outflows` is COST_OF_LIVING_CLASSES, exactly as the window's
 *  `income_this_month` / `outflows_this_month`. Server-computed. */
export interface MeansMonth {
  /** The month's first day, YYYY-MM-DD. */
  month: string
  income: number
  outflows: number
}

/** Something that began being counted in a point's stretch
 *  (`domain/tracking_start.py`): an account arriving with its opening balance,
 *  or a stated value or manual debt at its first dated point. `amount` is
 *  signed as the chart it rides on reads it — net worth's sign on Net Worth,
 *  Account Composition and Savings; owed (positive) on Liabilities. */
export interface TrackingEntry {
  /** `account`: a Starting Balance; `pre_start`: history from before the
   *  account's budget start, on an account that may already be drawn. */
  kind: 'account' | 'pre_start' | 'stated_asset' | 'manual_debt'
  id: string
  name: string
  day: string
  amount: number
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
  /** What entered net worth in the stretch this point closes. */
  entered: number
  entries: TrackingEntry[]
}

export interface NetWorthReport {
  points: NetWorthPoint[]
  unmanaged_liability_total: number
  asset_value_total: number
  /** Newest point less oldest, as drawn. */
  change: number
  /** The same, less what began being counted after the oldest point — the
   *  headline. Null with no points. */
  like_for_like_change: number | null
  /** `change` less `like_for_like_change`. */
  entered_total: number
  /** Figures told rather than added up, with the day each was last true. */
  stated_values: {
    kind: 'stated_asset' | 'manual_debt'
    id: string
    name: string
    value: number
    as_of: string | null
  }[]
  /** Figures in today's net worth unmoved for 60+ days
   *  (`tracking_start.STALE_AFTER_DAYS`). */
  stale_balances: {
    kind: 'account' | 'stated_asset' | 'manual_debt'
    id: string
    name: string
    last_changed: string | null
  }[]
  /** The threshold `stale_balances` was built with, for the page's copy. */
  stale_after_days: number
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
  /** At the minimum payment. Null when the terms are unset, and when the
   *  minimum never retires the debt — there is no interest bill to quote
   *  (backend `AmortizationResult.interest_to_payoff`). */
  total_interest_remaining: number | null
  /** The minimum-payment schedule never retires the debt. */
  baseline_never_pays_off: boolean
  /** The payoff verdict, measured at `payoff_basis`. */
  never_pays_off: boolean
  /** What that verdict was measured at: the pace actually paid, or the
   *  minimum when there is no payment history. Null without terms. */
  payoff_basis: 'observed' | 'minimum' | null
  /** The verdict's date (`amortization.payoff_verdict`). */
  payoff_date: string | null
  terms_complete: boolean
  /** Why there is no payoff at the pace paid, when there is none — the cell
   *  says this instead of "—" (`liability_service.pace_missing`). */
  pace_missing: 'no_terms' | 'payments_not_linked' | 'too_little_history' | null
  /** The entered payment contradicts the loan's own terms
   *  (`amortization.terms_check`) — most often escrow folded into it. */
  terms_disagree: boolean
}

export interface LiabilitiesBalancePoint {
  date: string
  /** Keyed by liability id; a debt is absent before its first point. */
  per_liability: Record<string, number>
  total: number
  /** Owed (positive) that began being counted this month, keyed to the
   *  liability. */
  entered: number
  entries: TrackingEntry[]
}

export interface LiabilitiesReport {
  items: LiabilitiesReportItem[]
  total_balance: number
  /** Sums only the rows with a finite interest bill */
  total_interest_remaining: number
  /** Rows left out of that total for want of terms */
  liabilities_missing_terms: number
  /** What those rows owe. */
  missing_terms_balance: number
  /** Rows owing anything today. */
  carrying_balance_count: number
  /** Rows left out of it because their minimum never retires the debt */
  liabilities_never_paying_off: number
  balance_over_time: LiabilitiesBalancePoint[]
  /** Owed on accounts closed with a balance still on them, excluded from
   *  `total_balance`. Net worth counts it, so the page says so rather than
   *  letting two figures labelled Total Liabilities disagree in silence.
   *  Narrowed by the report's type and mode filters, like `items`. */
  closed_with_balance_count: number
  closed_with_balance_total: number
}

export interface AccountCompositionPoint {
  date: string
  /** Balance per account-type key in `series` (custom types included). */
  balances: Record<string, number>
  /** The bands no account holds, so the stack sums to `net_worth`: stated
   *  asset values (positive) and debts with no account (negative). */
  stated_assets: number
  manual_debts: number
  /** Net worth at this point — served (report_service.account_composition)
   *  rather than summed from `balances`, because unmanaged debts and stated
   *  asset values sit in net worth without appearing in any account series. */
  net_worth: number
  /** The stated-asset share of the gap between the net line and the visible
   *  stack — footnoted when non-zero. */
  asset_value_total: number
  entered: number
  entries: TrackingEntry[]
}

export interface AccountCompositionReport {
  points: AccountCompositionPoint[]
  /** Every account type a live account has, registry order: a series'
   *  colour is its place here, so it holds across ranges. */
  series: string[]
}

/** One month of the Burn Rate chart: the 30 days ending on its last day
 *  (today, for this month) and the 60 before them per 30 days — the
 *  Overview's `burn_rate_30` / `burn_rate_prior_60` on the newest point.
 *  Server-computed: `domain/burn_rate.py`. */
export interface BurnRatePoint {
  date: string
  rolling_30: number
  prior_60: number
}

export interface BurnRateReport {
  points: BurnRatePoint[]
}

export interface SankeyNode {
  id: string
  name: string
  /** Left of the hub: an income source, an `inflow` (refunds, from savings,
   *  borrowed, re-planned) or the `shortfall` that balances the sides. The
   *  hub is `budget`. Right of it: groups (and their categories) or the
   *  `left_over` sink. Backend `domain/cash_flow.py`. */
  type:
    'income_payee' | 'inflow' | 'shortfall' | 'budget' | 'category_group' | 'category' | 'left_over'
  /** The entity this node stands for. `id` is a display key that may compose
   *  several ids — a category node is keyed by (group, category) so one
   *  category can sit under both its own group and the savings trunk. */
  entity_id?: string | null
  /** Spent-mode category nodes: the activity classes the node counted, which
   *  its drill-down must list. The Savings, Debt payments and Uncategorized
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

/** A payee band under a Sankey category: its payee of record's id, or null
 *  for "Other payees" and payee-less rows (backend `SankeyPayee`). */
export interface SankeyPayee extends CategoryPayee {
  payee_id: string | null
}

/** Sources → the hub (`__budget__`) → groups → categories, both sides of
 *  the hub balanced by a Left over or Shortfall node. Spent mode is net: a
 *  refund comes off its category, a withdrawal off what was saved. Backend
 *  `domain/cash_flow.py`. */
export interface CashFlowReport {
  nodes: SankeyNode[]
  links: SankeyLink[]
  /** Income vs Expenses' income for the same window. */
  total_income: number
  /** What the right side draws, Left over aside. */
  total_expense: number
  /** Net per class, as Income vs Expenses reads them. null in budgeted mode,
   *  which draws from assignments and has no activity class to split by —
   *  "not claimed", never zero. Savings and debt can be negative: more drawn
   *  out, or borrowed, than put in. */
  total_spending: number | string | null
  total_savings: number | string | null
  total_debt_principal: number | string | null
  /** Budgeted mode: assignments net of re-planning. null in spent mode. */
  total_assigned: number | string | null
  /** Spent mode: money in less money out — Income vs Expenses' `net` for the
   *  same window. null in budgeted mode, which has no such figure. */
  net: number | string | null
  category_payees: Record<string, SankeyPayee[]>
  group_categories: Record<string, CategoryPayee[]>
  /** Per category node whose drawn payees are wider than it: what came back
   *  (a refund from a payee with no charge in the window), drawn as a source
   *  at the payee level so that level balances too. */
  category_returns: Record<string, CategoryPayee>
}

/** The figures every Plan vs Spent cell, Total and month total carries —
 *  what an envelope had, spent and had left, carryover counted (backend
 *  `domain/plan.py` `envelope_outcome` / `across_months`). All served: never
 *  add the parts here. `funded - spent + other === left` for a month;
 *  `funded - spent + other + overspent === left` for a span. */
export interface PlanVsSpentFigures {
  assigned: number
  /** Money moved into the envelope — a transfer from savings, a deposit filed
   *  to it. It funds the envelope (backend `plan_effect`). */
  moved_in: number
  /** Non-negative: money moved out and not spent — a transfer to a
   *  brokerage, a principal payment from an untagged envelope. */
  moved_out: number
  /** Carried in + assigned + moved in − moved out. */
  funded: number
  /** Net of refunds; negative only when refunds beat the spending. */
  spent: number
  /** What the budget page's Available counts that the plan ledger does not —
   *  a pending row, a starting balance, a card refund repaying debt. Zero for
   *  an ordinary envelope. */
  other: number
  /** The budget page's Available at the end (a span's floored). */
  left: number
  /** What Ready to Assign covered when the envelope went negative. */
  overspent: number
}

/** One category-month of Plan vs Spent (backend `services/plan_vs_spent.py`). */
export interface PlanVsSpentCell extends PlanVsSpentFigures {
  month: string
  /** What the month before left, floored as the budget page carries it. Null
   *  where the page states no figure for the month before (counted as zero). */
  carried_in: number | null
  /** The verdict: negative by at least $1 and 1% of what it had. Tint by
   *  this, never by `left`'s sign — a few cents short is not over. Never true
   *  in the running month. */
  over: boolean
  /** Anything assigned, moved or spent, or money held. Served, as the count
   *  `months_active` reads it. */
  active: boolean
  /** `left` walked from the ledger: the budget page states no figure here. */
  estimated: boolean
}

/** A category over the complete months — the Total column: its months
 *  walked in order (backend `domain/plan.py` `across_months`). */
export interface PlanVsSpentTotal extends PlanVsSpentFigures {
  /** What the first complete month carried in; null where unknown. */
  carried_in: number | null
  /** The server's verdict: Ready to Assign covered at least $1 and 1%. */
  over: boolean
  estimated: boolean
}

export interface PlanVsSpentCategory {
  category_id: string
  category_name: string
  category_group_name: string
  monthly: PlanVsSpentCell[]
  months_over: number
  months_active: number
  avg_overspend: number
  /** Backend `domain/plan.py` `is_chronic`; the Guide reads the same flag. */
  chronic: boolean
  total: PlanVsSpentTotal
}

/** One month over every category — the totals row: its cells summed. */
export interface PlanVsSpentMonth extends PlanVsSpentFigures {
  month: string
  /** The running month: its figures are month-to-date. Drawn apart and
   *  labelled "so far" (`utils/reportMonths.ts`), never in an average, total
   *  or headline. Home: backend `domain.dates.ReportWindow`. */
  partial_month: boolean
  carried_in: number
  /** Categories over this month; 0 on the running month. */
  categories_over: number
}

export interface PlanVsSpentReport {
  months: string[]
  /** The newest of `months`, still running: its cells are month-to-date and
   *  labelled "so far"; no verdict or total reads it (backend
   *  `ReportWindow`). */
  running_month: string
  /** The dates the Total column and the window totals cover — the complete
   *  months — for the drills that open them. Null when there are none yet. */
  totals_start: string | null
  totals_end: string | null
  categories: PlanVsSpentCategory[]
  month_totals: PlanVsSpentMonth[]
  /** The categories' Totals summed, so the headline cannot say what the rows
   *  under it do not. */
  total_assigned: number
  total_moved_in: number
  total_moved_out: number
  total_funded: number
  total_spent: number
  total_other: number
  total_left: number
  total_overspent: number
  chronic_count: number
  /** A saved filter was named and could not be found — backend
   *  `CategoryScope` in `report_scope.py` says what the scope then holds. */
  filter_unavailable: boolean
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
  /** null on the Uncategorized line: spending with no category, drilled by
   *  `noCategory` (backend `domain/spending.py`). Net of refunds, so `total`
   *  can be negative. */
  id: string | null
  name: string
  parent_id: string | null
  /** Always named, the Uncategorized line's group too (server
   *  `domain/spending.py`): the page never names a group itself. */
  parent_name: string
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
  /** The activity classes these figures count, served so a drill-down lists
   *  exactly them (backend `ReportService._spending_rows`). Pass it as the
   *  drill's `activityClasses`, never a client copy of the class set. */
  counted_classes: string[]
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
  /** null on the Uncategorized row. */
  category_id: string | null
  category_name: string
  month: string
  /** Net of refunds: a month that took back more than it spent is negative. */
  total: number
}

export interface SeasonalityReport {
  cells: SeasonalityCell[]
  months: string[]
  /** The largest by net spending (backend `SEASONALITY_TOP`). */
  categories: { id: string | null; name: string }[]
  /** Every category that spent in the window — "top 20 of N". */
  category_count: number
  /** The activity classes these figures count, served so a drill-down lists
   *  exactly them (backend `ReportService._spending_rows`). Pass it as the
   *  drill's `activityClasses`, never a client copy of the class set. */
  counted_classes: string[]
}

/** One envelope or account the emergency fund counted. */
export interface FundPart {
  id: string
  name: string
  balance: number
}

/** What the household said it keeps outside IGAB. `declared` with a null
 *  `amount` is "I have this covered" — never zero. */
export interface FundExternal {
  declared: boolean
  amount: number | null
  as_of: string | null
  note: string | null
}

/** The emergency fund and exactly what it counted. Served — the home is
 *  backend/src/igab/services/emergency_fund.py (`EmergencyFundOut`): envelopes
 *  tagged Emergency fund, off-budget accounts marked "counts toward emergency
 *  fund", and anything kept elsewhere. Nothing is guessed; never recompute
 *  `total` here. */
export interface EmergencyFund {
  set_up: boolean
  /** Null only when nothing in IGAB was chosen and no figure was declared. */
  total: number | null
  categories: FundPart[]
  accounts: FundPart[]
  external: FundExternal
}

/** What a lean month costs — GET /reports/essentials. `essentials` is the
 *  Guide's figure and the Overview card's; the table averages complete months. */
/** One month of the emergency-fund coverage report. */
export interface CoveragePoint {
  month: string
  fund_balance: number
  /** The essentials figure as of this month (backend `essentials_at`): the
   *  three complete months ending here, so the newest point IS the headline and
   *  this line and the roadmap's target cannot tell different stories. */
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
  /** The emergency fund and what it counted — the Essentials report's own. */
  fund: EmergencyFund
  /** "Covered": the Essentials report's own `fund_runway`, quoted — the fund,
   *  what the cards owe taken out, over Essentials. The series is the fund
   *  alone, so its newest point and this differ by today's card debt. */
  covered: RunwayFigure
  essentials: EssentialsFigures
  /** How many Essential categories are also Long-term expense. None: the
   *  spread setting has nothing to spread, so its toggle is hidden and the
   *  page says why (`utils/essentialsFigures.ts`). */
  long_term_essentials: number
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
  /** The complete months the table's averages divide by: `months`, or fewer
   *  when the budget's history is younger (backend `history_window`). */
  months_averaged: number
  essentials: EssentialsFigures
  /** How many Essential categories are also Long-term expense. None: the
   *  spread setting has nothing to spread, so its toggle is hidden and the
   *  page says why (`utils/essentialsFigures.ts`). */
  long_term_essentials: number
  monthly_total_average: number
  categories: {
    category_id: string | null
    name: string
    group_name: string | null
    total: number
    monthly_average: number
    months_with_spend: number
  }[]
  /** As paid, never spread; `sinking_total` is the part of `total` filed to a
   *  sinking fund (Long-term expense). */
  monthly_series: { month: string; total: number; sinking_total: number }[]
  reserve: { months: number; amount: number }[]
  roadmap_range: [number, number]
  /** The emergency fund and what it counted, whatever the Guide tracks. */
  emergency_fund: EmergencyFund
  /** How long the fund lasts on Essentials, card debt taken out — the
   *  runway rule at (Essentials, the fund); `months` null when nothing was
   *  chosen or nothing is tagged Essential. */
  fund_runway: RunwayFigure
  /** Tagged Essential and still not counted, by class — see
   *  `CostOfLivingReport.class_excluded`. */
  class_excluded: SpendingClassExcluded[]
}

export interface SpendingTrendSeries {
  /** null on the Uncategorized series. */
  id: string | null
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
  /** `total` over the months the range holds whole and that are over —
   *  `months_averaged` of them (backend `complete_months_within`). Null with
   *  none: a range inside the running month has nothing to average. */
  avg_monthly: number | null
  months_averaged: number
  /** The running month when the range draws it: month-to-date, "so far". */
  running_month: string | null
  class_excluded: { activity_class: string; label: string; categories: number; total: number }[]
  /** The activity classes these figures count, served so a drill-down lists
   *  exactly them (backend `ReportService._spending_rows`). Pass it as the
   *  drill's `activityClasses`, never a client copy of the class set. */
  counted_classes: string[]
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
    /** The running month, month-to-date: drawn apart and labelled "so far",
     *  never in a headline (backend `ReportWindow`). */
    partial_month: boolean
    assigned: number
    activity: number
    /** Spent as every plan report counts it — net of refunds, and not the
     *  money moved in or out, which `activity` nets away (backend
     *  `services/plan_ledger.py`). */
    spent: number
    moved_in: number
    /** Non-negative: money moved out and not spent (backend `plan_effect`). */
    moved_out: number
    /** Null for an income category: "Income categories do not hold money", so
     *  their available is a lifetime carryover the budget page never draws.
     *  Their monthly activity is meaningful and is still served. Null too for
     *  a month before an import the history cannot reproduce — backend
     *  `CategoryHistoryMonth.available`. */
    available: number | null
  }[]
  /** `spent` averaged over the window's complete months — served, so the
   *  running month's month-to-date figure never pulls it down. */
  average_spent: number
  months_averaged: number
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
   *  every payee — Where it went's 80% line, which the top 25 cannot give
   *  (backend `domain/concentration.py`). null when nothing was spent. */
  payees_to_80pct: number | null
  /** Months of the window a payee must appear in to be `is_recurring`
   *  (backend `domain.spending.recurring_months`); null when the window is
   *  too short to call anything recurring. */
  recurring_min_months: number | null
  /** The activity classes these figures count, served so a drill-down lists
   *  exactly them (backend `ReportService._spending_rows`). Pass it as the
   *  drill's `activityClasses`, never a client copy of the class set. */
  counted_classes: string[]
}

export interface DayPatternItem {
  day_of_week: number
  day_name: string
  /** Net spending on this weekday across the window. */
  total: number
  /** Purchases, not rows: a split's legs are one purchase. */
  count: number
  /** How many of this weekday the window holds, quiet ones included. */
  weekdays: number
  /** `total / weekdays`: a typical such day. null when there are none. */
  avg_per_day: number | null
}

export interface DayPatternsReport extends SavedFilterScope {
  days: DayPatternItem[]
  /** Savings / debt activity in the categories the user selected that this
   *  chart will not count. Empty without a selection. */
  class_excluded: SpendingClassExcluded[]
  /** The activity classes these figures count, passed to the drill-down so a
   *  bar and the panel it opens total the same. */
  counted_classes: string[]
  /** The days `weekdays` counts: the range, from the budget's first
   *  transaction at the earliest, through today at the latest. */
  window_start: string
  window_end: string
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

/** One service — a payee inside a Subscription-tagged category — and what it
 *  costs a year. Served by `domain/subscriptions.py`; the page adds nothing
 *  up and decides nothing about cadence. */
export interface SubscriptionService {
  payee_id: string | null
  payee_name: string
  /** How `annual` was arrived at: the last 12 complete months' charges
   *  ("observed"), projected from the latest charge for a service younger than
   *  that year ("new") or one whose price changed ("price_change"), or zero
   *  because it has had no charge for 1.5 cycles ("stopped"). */
  basis: 'observed' | 'new' | 'price_change' | 'stopped'
  /** Net of refunds; zero when stopped. */
  annual: number
  /** annual ÷ 12 */
  monthly: number
  interval_days: number
  /** "monthly"/"yearly" are calendar cadences; "days" is every `interval_days`. */
  cadence: 'monthly' | 'yearly' | 'days'
  /** One charge says nothing about cadence, so monthly was assumed. */
  cadence_assumed: boolean
  latest_charge: number
  first_charge_date: string
  last_charge_date: string
  charges_in_year: number
  refunded_in_year: number
}

export interface SubscriptionCategory {
  category_id: string
  category_name: string
  group_name: string
  /** The sum of its services' annual. */
  annual: number
  monthly: number
  /** Net charges per month of `months` — the chart. The range picker moves
   *  only these. */
  monthly_amounts: number[]
  total: number
  last_charge_date: string
  services: SubscriptionService[]
}

export interface SubscriptionsSummary {
  /** The sum of every category's `annual`. */
  total_annual: number
  /** total_annual ÷ 12 */
  total_monthly: number
  /** Categories with a service still charging, of `tagged_categories`. */
  charged_categories: number
  tagged_categories: number
  new_this_month: number
  /** Services whose annual is projected ("new" or "price_change"). */
  projected_services: number
  stopped_services: number
}

export interface SubscriptionsReport {
  subscriptions: SubscriptionCategory[]
  summary: SubscriptionsSummary
  /** The chart's complete months. */
  months: string[]
  /** Every listed category's month, summed — the height of each stacked bar. */
  monthly_totals: number[]
  /** The 12 complete months `annual` reads, whatever the range says. */
  year_start: string
  year_end: string
}

/** An envelope's target on the Savings report, judged as the Budget page
 *  judges it this month. */
export interface SavingsTarget {
  type: string
  amount: number
  target_date: string | null
  /** The Budget page's pill (`TargetService.calculate_status`). */
  status: TargetStatus
  /** Available ÷ amount for a savings-balance target, floored at 0 and NOT
   *  capped at 1. null for a funding target, which asks for a pace. */
  progress: number | null
}

export interface SavingsEnvelope {
  category_id: string
  category_name: string
  group_name: string
  /** Available at each month's end, from the Budget page's own walk
   *  (BudgetService.envelope_series). `null` where no figure can be stated —
   *  before an import the history cannot reproduce; see
   *  `SavingsReport.unrecovered`. Absent, not zero: draw a gap. */
  monthly_balances: (number | null)[]
  current_balance: number
  /** Positive assignments in the window. */
  total_inflow: number
  target: SavingsTarget | null
}

/** An off-budget account that counts as savings (`txn_filters.SAVINGS_ACCOUNT`).
 *  On-budget accounts are never listed: their money is in the envelopes. */
export interface SavingsAccount {
  account_id: string
  name: string
  account_type: string
  /** Balance through each month's end; null before the account's first row. */
  monthly_balances: (number | null)[]
  current_balance: number
}

/** Kept-here Savings and Emergency fund envelopes plus off-budget savings
 *  accounts. Envelopes count at their carryover-floored Available. */
export interface SavingsSaved {
  total: number
  envelopes_total: number
  accounts_total: number
  /** Set aside at each month's end, aligned with `SavingsReport.months`;
   *  null before anything in the section has a figure. */
  monthly_totals: (number | null)[]
  /** What savings accounts brought in by being linked, per month. */
  monthly_entered: number[]
  monthly_entries: TrackingEntry[][]
  envelopes: SavingsEnvelope[]
  accounts: SavingsAccount[]
}

/** On the way to savings, or Sinking funds — never added to Saved. */
export interface SavingsSection {
  total: number
  envelopes: SavingsEnvelope[]
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

/** The Savings report in three parts — home is backend
 *  `services/savings_report.py`. */
export interface SavingsReport {
  saved: SavingsSaved
  /** What sent-out Savings envelopes hold until the money leaves. */
  on_the_way: SavingsSection
  /** Long-term expense envelopes that are not savings. */
  sinking_funds: SavingsSection
  months: string[]
  /** Moves out of Savings and Emergency fund envelopes, not sinking funds. */
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
  /** The baseline's mean one σ either way, floored at zero: "usually $a–$b". */
  usual_low: number
  usual_high: number
  z_score: number
  direction: 'high' | 'low'
  /** True when `month` is the month still in progress, so `actual` is a
   *  month-to-date figure — backend `services/report_stats.anomaly_scan`,
   *  which also says why those rows are always `direction: 'high'`. Never
   *  recompute it here from `month` and the clock: which month the report
   *  calls "in progress" is the server's, and it is what scored the row. */
  partial_month: boolean
  /** Twelve calendar months ending with `month`; null before the category's
   *  first spending in the window — absent, not zero. */
  history: (number | null)[]
}

export interface AnomalyReport {
  anomalies: AnomalyItem[]
  /** Categories with spending in the window, sinking funds aside. */
  categories_seen: number
  /** Of those, how many had six earlier months to be scored against. */
  categories_tested: number
  /** Long-term expense categories, which are never tested. */
  sinking_funds_skipped: number
}

export interface PaydayEffectDay {
  offset: number
  /** The median payday's discretionary spending this many days after it. */
  median_spend: number
  /** Paydays this day has happened for. */
  paydays: number
}

export interface PaydayEffectReport {
  days: PaydayEffectDay[]
  /** The median day's discretionary spending across the whole window, over
   *  `baseline_days` days. null only when there were no paydays. */
  baseline_daily: number | null
  baseline_days: number
  /** Paydays found in the window. */
  event_count: number
  window_start: string
  window_end: string
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
  /** The first day the median path is below zero. */
  goes_negative_date: string | null
  /** The first day the 1-in-10 low band is below zero — never later than
   *  `goes_negative_date`. Backend `domain/cash_projection.py`; the softer
   *  warning reads it (`cashProjectionView.projectionWarning`). */
  p10_negative_date: string | null
  /** The runway at every choice the page offers, each with its burn-down. */
  if_income_stopped: IfIncomeStopped
}

/** One "If income stopped" choice: the runway, and its straight burn-down —
 *  today's money, then zero on `runs_out_on` or the balance at the horizon
 *  (`domain/runway.burn_down`). */
export interface StoppedIncomeOption extends RunwayFigure {
  line: { date: string; balance: number }[]
}

export interface IfIncomeStopped {
  /** Every spending × money choice, in picker order. */
  options: StoppedIncomeOption[]
  /** The Overview's choice, which the pickers open on. */
  default_spending: RunwaySpending
  default_money: RunwayMoney
  fund_chosen: boolean
  essentials_known: boolean
  window_start: string | null
  window_end: string | null
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
  skip_reasons?: Record<string, number>
  matched: number
  adopted: number
  review_queued: number
  cleared: number
  removed_pending: number
  /** See api/simplefin.ts for the shapes; typed there so the summary formatter
   *  can read a single-connection result and a sync-all the same way. */
  orphaned_links: import('../api/simplefin').OrphanedLink[]
  bank_errors: import('../api/simplefin').BankError[]
  balance_drift: import('../api/simplefin').BalanceDrift[]
  /** Opening balances the run declined to write. See api/simplefin.ts. */
  refused_anchors?: string[]
  /** First syncs that wrote no opening balance because the account already
   *  had history. Informational. See api/simplefin.ts. */
  anchors_skipped_for_history?: string[]
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
  /** null for the Uncategorized bucket — the flag its drill reads (backend
   *  `report_basics.cost_of_living`). Never test the name. */
  group_id: string | null
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
  avg_monthly_income: number
  /** Spending outside both tiers over the same window — the Discretionary
   *  report's own rows — so the verdict lays take-home out whole: committed,
   *  discretionary and left over (`necessityView.takeHomeSplit`). Null when
   *  nothing is tagged, as that report serves it. */
  avg_monthly_discretionary: number | null
  /* The gap between the tiers, and the two ratios against take-home, are NOT
   * served: they are arithmetic on the three averages above, so they are
   * composed once in `components/reports/charts/necessityView.ts`
   * (`nonEssentialSpend`, `necessityShare`). */
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

/** One category's discretionary spending over the window. */
export interface DiscretionaryLine {
  category_id: string
  category_name: string
  total: number
  avg_monthly: number
}

export interface DiscretionaryGroup {
  /** Null on the Uncategorized line: rows with no category at all, drilled by
   *  `no_category` — an empty id list would filter nothing and open the whole
   *  window. */
  group_id: string | null
  group_name: string
  total: number
  avg_monthly: number
  /** Biggest first. Empty on the Uncategorized line, which is one line. */
  categories: DiscretionaryLine[]
}

/** Spending outside Cost of living (backend
 *  `domain.activity_class.DISCRETIONARY_ROW`): SPENDING-class rows in no
 *  category tagged Essential or Cost of living, net of refunds. Not the Cost of
 *  Living report's "Committed, not essential", which is Cost of living minus Essentials. */
export interface DiscretionaryReport {
  months: string[]
  /** How many months `avg_monthly` divides by: every entry of `months`, all
   *  complete. */
  months_averaged: number
  /** The window the figures cover, served so a drill asks for the same days. */
  window_start: string
  window_end: string
  /** The wide tier's basis. Never 'bound': the Guide's bindings are the
   *  Essentials figure's, not this report's. */
  basis: 'tag' | 'all'
  /** False when nothing is tagged Essential or Cost of living. Every figure
   *  below is then null and `groups` empty: "outside Cost of living" would be
   *  the whole burn rate, so the page shows what to tag instead. */
  tagged: boolean
  total: number | null
  avg_monthly: number | null
  /** One per entry of `months`; empty when `tagged` is false. */
  monthly_totals: number[]
  /** The SPENDING class over the same window, which `total` is a part of. The
   *  share between them is composed in `discretionaryView.ts`, not served. */
  spending_total: number | null
  /** The Cost of living tier over the same window, positive. With `total` it
   *  is `spending_total` plus the debt payments that tier counts by class —
   *  said in one line (`discretionaryView.tierSumLine`). Null untagged. */
  cost_of_living_total: number | null
  groups: DiscretionaryGroup[]
}

export interface WishlistDisciplineReport {
  cooled_then_bought: number
  cooled_then_dropped: number
  bought_early: number
  /** Dropped before the cooling-off period ended — resisted money, but not
   *  something the cooling-off period did. */
  dropped_early: number
  still_open: number
  /** Open wishes past their wait (or with none) — waiting on a decision, not
   *  the calendar — and the rest of `still_open`. Served: whether a wish is
   *  cooling is the server's `guide.wishlist.is_cooling`, on the reader's
   *  day. */
  ready_to_decide: number
  still_cooling: number
  /** Decided wishes the server can place against their wait, how many came
   *  after it, and that share — the report's headline. Null with nothing
   *  decided, which is not 0%. */
  decided_count: number
  waited_out_count: number
  waited_out_share: number | null
  /** Every dropped wish's cost, waited on or not. */
  resisted_total: number
  /** How many wishes `resisted_total` sums — the card's count. */
  resisted_count: number
  bought_total: number
  /** How many wishes `bought_total` sums. */
  bought_count: number
  open_total: number
  /** Mean days from adding a wish to buying it. */
  avg_days_to_buy: number | null
  avg_wish_cost: number | null
  unplaced: number
  /** The person's own waiting period for new wishes, in days. */
  cooling_days: number
}
