"""Shared transaction-filter predicates encoding the money-aggregation rules.

Two query shapes exist and must never be mixed up:

- PARENT_ROW: rows that carry account-balance meaning. A split parent's amount
  equals the sum of its children, so account/cash-flow sums use parent rows
  (split children would double-count).
- LEAF: rows that carry category meaning. Categories live on split children
  and plain transactions; split parents have no category. Category-keyed sums
  use leaf rows (a parent row would hide every split's category activity).

POSTED excludes pending bank transactions from every money aggregate: pending
amounts are provisional (auth holds change at posting), so money moves exactly
once — when the transaction posts. This mirrors AccountRepository.get_balance.
"""

from datetime import date

from sqlalchemy import Boolean, and_, func, not_, or_, select
from sqlalchemy.orm import aliased

from igab.db.models import (
    Account,
    Category,
    Payee,
    Tag,
    Transaction,
    category_tags,
    payee_tags,
)
from igab.domain.payee_names import BALANCE_ADJUSTMENT_PAYEES
from igab.repositories.category_filters import IN_SYSTEM_GROUP, SPENDABLE, SPENT_ENVELOPE

NOT_DELETED = Transaction.is_deleted == False  # noqa: E712
POSTED = Transaction.cleared != "pending"
LEAF = Transaction.is_split == False  # noqa: E712
PARENT_ROW = Transaction.parent_transaction_id.is_(None)

#: Rows that carry account-balance meaning. Composed rather than respelled:
#: every balance sum in the app wants exactly these three, and spelling them
#: by hand is how `get_balance` and the guide's `_account_balance` came to
#: disagree about whether a pending auth hold is money.
BALANCE_ROW = and_(NOT_DELETED, PARENT_ROW, POSTED)

#: The bank has confirmed this row. Implies POSTED — 'pending' is not in the
#: set — but the two are kept separate because they answer different
#: questions: POSTED is "has this moved", CLEARED is "has the bank agreed".
CLEARED = Transaction.cleared.in_(("cleared", "reconciled"))

#: Bank-identity states of a row, for the sync's candidate search.
#:
#: BANK_UNLINKED — no bank id at all: a YNAB/CSV import or a hand-typed row.
#:
#: PROVISIONALLY_LINKED — carries a bank id, but the bank has not posted
#: against it yet (`bank_posted_date` is NULL): either a pending row the sync
#: created, or a user row matched while the bank record was still an auth
#: hold. A bank that re-identifies the record at posting reports a "new"
#: posted record whose only existing counterpart is one of these — so a
#: posted feed record may claim them (same amount, the usual date rules); a
#: pending feed record never may.
#:
#: The `cleared` guard is load-bearing. Rows linked before `bank_posted_date`
#: existed are `cleared` with a NULL posted date; without the guard every one
#: of them could absorb a foreign same-amount bank id.
BANK_UNLINKED = Transaction.sync_id.is_(None)
PROVISIONALLY_LINKED = and_(
    Transaction.sync_id.isnot(None),
    Transaction.bank_posted_date.is_(None),
    Transaction.cleared.in_(("pending", "uncleared")),
)

#: A row the user (or their file import) wrote and no bank feed has touched —
#: what the review-queue matcher pairs a freshly synced row against.
#: `sync_id` alone misses id-less feeds: a sync-created row without a bank id
#: is still bank-sourced, never a "manual" match candidate.
USER_ENTERED = and_(
    Transaction.import_id.is_(None),
    Transaction.sync_id.is_(None),
    Transaction.sync_source.is_(None),
    Transaction.linked_transaction_id.is_(None),
)


def sync_created_pending(source: str):
    """A pending row the named feed itself wrote. Never a user row: only
    the sync sets `pending`, and it always stamps its source."""
    return and_(
        Transaction.cleared == "pending",
        Transaction.sync_source == source,
        Transaction.sync_id.isnot(None),
    )


def not_future(as_of: date):
    """Rows dated on or before `as_of`.

    A function, not a constant: a module-level `Transaction.date <= today()`
    would freeze the date at import time and quietly go stale in a
    long-running process.

    **This is deliberately NOT part of CLEARED, and the two callers of
    CLEARED differ by exactly this predicate.** They are asking different
    questions, and forcing them into agreement would break one of them:

    - The account header reports a partition — `balance`, `cleared_balance`
      and `uncleared_balance`, where the first is the sum of the other two.
      Applying a cutoff to only one term does not remove a future-dated
      cleared row from the header; it relabels it as *uncleared*, which is a
      worse answer than the one it replaced. Applying it to all three hides
      a transaction the register plainly shows.
    - Reconciliation asks what today's bank statement should say, and a
      statement cannot reflect what has not happened. `get_status` therefore
      adds this cutoff, and `finish()` sizes its adjustment against the
      result — so the adjustment is correct even while the header differs.
    - Ready to Assign is a statement about a month:
      `AccountRepository.sum_on_budget_balance` bounds the budget's cash to
      the viewed month's end, as category activity already is, so a row
      dated next month cannot lower this month's figure before it reaches
      any envelope.

    The divergence is bounded to exactly the future-dated cleared rows, and
    is pinned by a test. Do not "fix" it into agreement.
    """
    return Transaction.date <= as_of


# A transfer leg, by either of the two signals that mark one. The partner link
# is the strong signal, but it is not always present: a YNAB import writes legs
# whose partner never appears (the partner account was skipped, or the leg's
# categorized counterpart never entered the pairing pool) so that balances stay
# right. Those rows are still transfers, and recognizing them only by
# `transfer_id` counted them as real income or expense.
# EXISTS, not `payee_id IN (subquery)`. `NULL IN (non-empty set)` is UNKNOWN,
# and `NOT UNKNOWN` is UNKNOWN — so the negation below silently dropped every
# payee-less row from every query using it, but only once the budget had at
# least one transfer payee to make the subquery non-empty. EXISTS is two-valued
# and cannot reproduce that.
TRANSFER_PAYEE = (
    select(Payee.id)
    .where(Payee.id == Transaction.payee_id, Payee.transfer_account_id.isnot(None))
    .correlate(Transaction)
    .exists()
)
TRANSFER_LEG = or_(Transaction.transfer_id.isnot(None), TRANSFER_PAYEE)
NON_TRANSFER = ~TRANSFER_LEG

# A row under one of the auto-generated bookkeeping names is a ledger
# correction, not spending anybody did — the set and its story live in
# `domain/payee_names.py` beside the writers' own spellings. EXISTS for the
# same NULL reason as TRANSFER_PAYEE above: a payee-less row must read as
# "not an adjustment", never as UNKNOWN.
BALANCE_ADJUSTMENT_ROW = (
    select(Payee.id)
    .where(Payee.id == Transaction.payee_id, Payee.name.in_(BALANCE_ADJUSTMENT_PAYEES))
    .correlate(Transaction)
    .exists()
)

#: A row that could still be joined to a partner: live, whole (not a split
#: parent and not one of its children), and not already linked.
#:
#: Composed rather than respelled because two callers need exactly this set and
#: they must not drift: the editor's candidate picker
#: (`find_transfer_candidates`) and the sync-time pairing pass
#: (`list_pairable_legs`). Note it deliberately does NOT require a transfer
#: payee — that is the whole point. Two synced legs of one movement arrive with
#: ordinary bank payees on both sides, which is why nothing paired them and why
#: an unpaired savings transfer inflated Ready to Assign by its own amount.
PAIRABLE_LEG = and_(NOT_DELETED, PARENT_ROW, LEAF, Transaction.transfer_id.is_(None))

_partner = aliased(Transaction)

#: The account on the other side of a transfer. The partner link is the strong
#: signal; an orphaned leg falls back to the account its transfer payee names,
#: the same signal TRANSFER_LEG uses to recognise it at all.
#
# `.correlate(Transaction)` is load-bearing. These nest inside another scalar
# subquery whose FROM is `accounts`, and SQLAlchemy only auto-correlates
# against the immediately enclosing SELECT — without it the planner adds
# `transactions` to the inner FROM and the subquery cross-joins.
COUNTERPART_ACCOUNT_ID = func.coalesce(
    select(_partner.account_id)
    .where(_partner.id == Transaction.transfer_id)
    .correlate(Transaction)
    .scalar_subquery(),
    select(Payee.transfer_account_id)
    .where(Payee.id == Transaction.payee_id)
    .correlate(Transaction)
    .scalar_subquery(),
)

#: Does this transfer leg point out of the budget? Coalesced so an
#: unresolvable counterpart reads as "no" rather than NULL — a NULL here would
#: poison every OR it takes part in, which is the bug TRANSFER_PAYEE just fixed.
_COUNTERPART_ON_BUDGET = func.coalesce(
    select(Account.on_budget)
    .where(Account.id == COUNTERPART_ACCOUNT_ID)
    .correlate(Transaction)
    .scalar_subquery(),
    True,
    type_=Boolean,
)
COUNTERPART_OFF_BUDGET = not_(_COUNTERPART_ON_BUDGET)

# Cash-flow rows: plain transactions, categorized transfer legs (YNAB spending
# transfers), and any leg pointing OUT of the budget. That last case is money
# genuinely leaving: a transfer to a brokerage or a mortgage is not internal
# movement just because the user left it uncategorized, and excluding it made
# the saving it represents invisible to every cash-flow report.
#
# Transfers between two on-budget accounts stay out — both legs sit inside the
# budget, so counting either double-counts. That asymmetry is the point: only
# the on-budget leg of an out-of-budget transfer passes, never the tracked side.
CASH_FLOW_ROW = or_(~TRANSFER_LEG, Transaction.category_id.isnot(None), COUNTERPART_OFF_BUDGET)
#: An account the arithmetic may still see. Soft-deleting an account cascades
#: its transactions today, so this looks redundant — but the balance term
#: (`sum_on_budget_balance`) filters deleted accounts while the activity-side
#: predicates below used not to, and Ready to Assign is an identity between
#: the two: any path that ever flags an account without cascading would move
#: the figure with no transaction to explain it. The two sides must be built
#: from one predicate, not two that happen to agree.
LIVE_ACCOUNT = Account.is_deleted == False  # noqa: E712

# Budget cash flow happens on on-budget accounts: plain activity inside
# tracking accounts (dividends, market adjustments, loan interest) moves net
# worth, not budget income/expense. Categorized spending-transfer legs already
# live on the on-budget side (service-enforced), so they pass. Reports that
# take an explicit account filter let the user's selection override this.
# Correlated to the row's own budget: the callers all reach this through a
# budget-scoped category or budget_id filter today, but that is a property of
# the call sites, not of the predicate — a caller filtering by account or
# date alone must not match another budget's accounts.
ON_BUDGET_ACCOUNT = Transaction.account_id.in_(
    select(Account.id)
    .where(
        LIVE_ACCOUNT,
        Account.on_budget == True,  # noqa: E712
        Account.budget_id == Transaction.budget_id,
    )
    .correlate(Transaction)
)

#: A card, for the credit model: an on-budget liability-classified account.
#: Classification, not `account_type == "credit_card"` — a custom on-budget
#: liability type (a HELOC, a line of credit) behaves identically, and the
#: type string would silently exempt it. Cards are excluded from the budget's
#: cash and never charge Ready to Assign; money reaches them only through
#: their set-aside envelope (domain/cards.py).
CARD_ACCOUNT = and_(
    LIVE_ACCOUNT,
    Account.on_budget == True,  # noqa: E712
    Account.classification == "liability",
)
ON_CARD_ACCOUNT = Transaction.account_id.in_(
    select(Account.id)
    .where(CARD_ACCOUNT, Account.budget_id == Transaction.budget_id)
    .correlate(Transaction)
)
#: The row is not older than its account's place in the budget.
#:
#: A synced account arrives with whatever history the bank kept, and that
#: history is opening balance, not activity anyone budgeted for. A card
#: brought in with three months of it filled the grid with red for money
#: spent before the budget knew the card existed — and the answer to that
#: red is to pay the card down, not to cover it from Ready to Assign.
#:
#: So such rows are left uncategorized on purpose, and this is what stops
#: the app asking about them forever. Written once, here, because "unfiled
#: work" is decided in exactly one place (`NEEDS_CATEGORY`) and a second
#: spelling of the date comparison is how the badge and the filter would
#: come to disagree about the same row.
#:
#: NULL `budget_start_date` — every account until someone answers — passes.
#: Correlated like `ON_BUDGET_ACCOUNT`, not a bare column comparison: every
#: caller of `NEEDS_CATEGORY` selects from Transaction alone, and a reference
#: to `Account.budget_start_date` would quietly add a cross join and multiply
#: the badge's count by the number of accounts.
AFTER_BUDGET_START = (
    select(Account.id)
    .where(
        Account.id == Transaction.account_id,
        or_(
            Account.budget_start_date.is_(None),
            Transaction.date >= Account.budget_start_date,
        ),
    )
    .correlate(Transaction)
    .exists()
)

#: The budget's cash: on-budget and not a card. This is the balance term of
#: Ready to Assign; a card's debt lives beside its set-aside, not in cash.
CASH_ACCOUNT = and_(
    LIVE_ACCOUNT,
    Account.on_budget == True,  # noqa: E712
    Account.classification != "liability",
)


#: A transfer leg whose partner never arrived: the payee names another account,
#: but no row links back. Balances stay right — both sides were written — but
#: nothing marks the row as internal movement, so reports read it as real
#: income or spending until someone disbelieves a chart.
#:
#: A YNAB import produces these in bulk when an account is left out: the far
#: leg is never created, so there is nothing to pair with. One real import
#: made 1,117.
#:
#: Note this is NOT the existing `is_transfer` filter, which tests
#: `transfer_id` alone — `is_transfer=false` returns every ordinary
#: transaction as well as these.
#:
#: `category_id IS NULL` is the third condition and it is load-bearing. A
#: *categorized* transfer leg is a YNAB spending transfer: deliberately
#: unpaired, and correctly counted as spending because the category is the
#: whole point. The importer knows this — it only ever tries to pair
#: uncategorized legs (`importer.py`: `payee.startswith("Transfer : ") and
#: category_id is None`) — so without this condition the predicate counts 169
#: rows on a real export that the importer does not, and the hygiene panel
#: promises a number the list it links to cannot show. Same definition, both
#: sides; asserted against a real import in test_ynab_import.py.
UNPAIRED_TRANSFER_LEG = and_(
    TRANSFER_PAYEE,
    Transaction.transfer_id.is_(None),
    Transaction.category_id.is_(None),
)


#: A row the user still has to file: no category, and it is the kind of row a
#: category is *for*.
#:
#: The three exclusions all matter, and each was wrong somewhere before this
#: existed:
#:
#: - `LEAF` — a split parent carries no category by design; its legs do.
#: - `ON_BUDGET_ACCOUNT` — off-budget rows (market movement, payroll
#:   contributions, loan interest) are net-worth movement, not spending
#:   awaiting a category.
#: - `CASH_FLOW_ROW` — the load-bearing one. Testing `transfer_id IS NULL`
#:   instead recognises only a *linked* transfer, so a leg whose partner never
#:   turned up (a skipped account, an unmatched pair) was counted as needing a
#:   category. A real YNAB import produced 1,117 of those. `CASH_FLOW_ROW`
#:   reads TRANSFER_LEG, which knows a transfer by its payee as well as its
#:   link — and it keeps the case that genuinely does need one: a transfer to
#:   an OFF-budget account is a mortgage payment, and budgeting for it is the
#:   whole point.
#:
#: Stated as an invariant: **needs a category** agrees with **counts as budget
#: cash flow**. A row that does not count cannot need one; a row that counts
#: and has none, does. `CASH_FLOW_ROW`'s middle arm (`category_id IS NOT NULL`)
#: is dead here because of the first condition, so the two compose exactly.
#: POSTED is deliberately NOT part of this. Whether a category applies to a row
#: is a fact about the row; whether it is *work the user can do now* is a
#: question the caller asks. Counters (the badge, the per-account count) add
#: POSTED because a pending amount is provisional and often arrives with its
#: payee. The Uncategorized filter does not, because a filter shows rows that
#: match rather than tallying a workload. That divergence is intended, is
#: bounded to exactly the pending uncategorized rows, and is pinned by a test —
#: do not "fix" it into agreement.
#:
#: The second narrowing is `AFTER_BUDGET_START`: a row that predates its own
#: account's arrival in the budget is opening position, not unfiled work. See
#: `Account.budget_start_date` — NULL there means the account never answered
#: the question, and nothing changes.
NEEDS_CATEGORY = and_(
    Transaction.category_id.is_(None),
    LEAF,
    ON_BUDGET_ACCOUNT,
    CASH_FLOW_ROW,
    AFTER_BUDGET_START,
)


#: The rows a liability's own ledger is made of, by kind. The line is the one
#: `domain/activity_class.py` already draws for reports: a transfer leg on a
#: tracked debt is principal moving (`TRANSFER_INTERNAL` / `DEBT_PRINCIPAL`),
#: a plain row on it is "Interest & fees" (`DEBT_INTEREST`). So a payment is
#: money that ARRIVED FROM ANOTHER ACCOUNT, and only that — not the month's
#: net movement, which subtracted YNAB's interest rows from the payment and
#: then accrued the same interest again from the rate, so a $3,000 mortgage
#: payment read as $1,382 and "never pays off". A plain deposit typed onto
#: the loan (no partner account) is deliberately NOT a payment: the register
#: and the reports call it interest & fees too, and counting it here would
#: make YNAB's balance adjustments into payments. `PLAIN_DEPOSIT_ROW` exists
#: so the liability page can say that such rows are being left out.
LOAN_PAYMENT_ROW = and_(BALANCE_ROW, Transaction.amount > 0, TRANSFER_LEG)
DEBT_INTEREST_ROW = and_(BALANCE_ROW, Transaction.amount < 0, NON_TRANSFER)
PLAIN_DEPOSIT_ROW = and_(BALANCE_ROW, Transaction.amount > 0, NON_TRANSFER)

#: The counterpart of a transfer leg is one of the budget's cash accounts.
#: Two-valued: EXISTS, never NULL, so it is safe under negation.
COUNTERPART_IS_CASH = (
    select(Account.id)
    .where(Account.id == COUNTERPART_ACCOUNT_ID, CASH_ACCOUNT)
    .correlate(Transaction)
    .exists()
)

#: Money reaching a card from the budget's own cash: the outflow side of the
#: card's set-aside envelope (`sum_card_payments_by_month`).
#:
#: Shape-free on purpose — the caller adds its own row shape — because
#: `UNCLAIMED_CARD_ROW` below is defined as the negation of this. Written
#: out twice, the two stop being complements: the first spelling required
#: `NON_TRANSFER` on the credit side while this side required a *cash*
#: counterpart, so a card paid off from an off-budget account, or a card→card
#: balance transfer, satisfied neither and fell into no term at all. The
#: reserve identity then read the whole set-aside as drift, on a history that
#: is perfectly ordinary.
CARD_PAYMENT_FROM_CASH = and_(Transaction.amount > 0, TRANSFER_LEG, COUNTERPART_IS_CASH)


def row_category(predicate):
    """A row whose own category satisfies a `category_filters` predicate.

    EXISTS rather than `category_id IN (subquery)`: two-valued, so it is safe
    under negation, and a row with no category simply fails it — exactly the
    trap `TRANSFER_PAYEE` and `IN_SYSTEM_GROUP` each document. This is the one
    lift from a category rule to a row rule; spelling a second one inline is
    how "the row's category is in a system group" came to exist twice.
    """
    return (
        select(Category.id)
        .where(Category.id == Transaction.category_id, predicate)
        .correlate(Transaction)
        .exists()
    )


#: A card row the budget has no claim on: **the complement**, written as
#: one, of the two sums that DO claim card rows —
#:
#: - not a payment from the budget's cash — `CARD_PAYMENT_FROM_CASH` above,
#:   the same expression `sum_card_payments_by_month` selects on;
#: - not a category's own money coming back — `category_filters.SPENDABLE`,
#:   the same expression that picks the ids handed to
#:   `sum_credit_outflows_by_category`.
#:
#: Both sides read the same two constants, so they cannot stop being
#: complements. They stopped twice when they were spelled out separately, and
#: the second time it was this line: `category_id IS NULL` is not the negation
#: of "the row's category is spendable", and the gap between them is precisely
#: a row filed to a category that exists but cannot release — a system-group
#: (income) category, a card's own envelope, a soft-deleted one. A rewards
#: credit filed to Ready to Assign therefore reduced a card's balance and
#: reached no term at all: reported as drift, permanently, growing with every
#: such row. `NOT EXISTS` subsumes the NULL case rather than naming it.
#:
#: What is left is a partner paying the card themselves, a promotional credit,
#: a bank adjustment, a balance transfer from another card, a rebate the user
#: called income — and, in the other direction, a charge that has arrived from
#: bank sync and not been filed yet, or a cash advance. It moves what is owed
#: and touches no envelope, which is correct — and is exactly why the reserve
#: identity has to name it rather than read it as drift
#: (`domain/cards.py reserve_discrepancy`, bounds T1 and T3).
#:
#: **Both signs, and the sum is a signed net.** This carried `amount > 0`
#: until 2026-08-30, so it claimed only the credits. An unfiled *charge*
#: reached no term at all — and any budget with live bank sync grows those
#: continuously, by construction. Worse, the half-claim made the check lie:
#: T1's left side moves by the NET of these rows and its allowance by the
#: POSITIVE half, so on a real card the bound cleared by a margin equal, to
#: the cent, to the rows it could not see. It passed by exactly the amount it
#: was failing to count, and only because the sign happened to fall that way
#: ("Two Ledgers, One Debt"). A complement is a complement in both
#: directions or it is a third spelling waiting to drift.
#:
#: **Shape: LEAF, matching `sum_credit_outflows_by_category`**, because the
#: question this asks — did a category claim this money? — is answered on the
#: leg, not on the parent. Under `PARENT_ROW` a split parent is uncategorized
#: *by construction*, so a split refund on a card was counted here AND as its
#: legs' release: the same money in two terms, widening T1 and T3 by its own
#: amount and hiding real drift of that size. Mixing the two shapes is the
#: trap this module's docstring opens with.
UNCLAIMED_CARD_ROW = and_(
    NOT_DELETED,
    LEAF,
    POSTED,
    ON_CARD_ACCOUNT,
    not_(row_category(SPENDABLE)),
    not_(CARD_PAYMENT_FROM_CASH),
)

#: A charge on a card filed to an income category: money going out, claimed as
#: money coming in. Not an integrity failure — the arithmetic matches an
#: uncategorized row — but a visibility one: the envelope term skips system
#: groups, so the spending lands in Uncovered with no envelope ever naming it.
#:
#: Two exclusions, one rationale. Cash accounts are out of scope entirely: an
#: income-filed outflow there is YNAB's own convention for a reconciliation
#: adjustment. And on cards, rows under a `BALANCE_ADJUSTMENT_PAYEES` name are
#: skipped by payee — YNAB writes the *identical* adjustment when reconciling
#: a card, and encoding the skip as "cash accounts only" read twelve imported
#: reconciliation rows and a starting balance as thirteen card charges filed
#: as income. Ledger corrections are not spending to give an envelope.
#:
#: Two readers, one spelling: the hygiene check counts these
#: (`account_hygiene._card_rows_filed_as_income`) and the repair script
#: unfiles them (`scripts/repair_card_payment_transfers.py`). They disagreed
#: about adjustment rows for exactly as long as each spelled this itself.
CARD_ROW_FILED_AS_INCOME = and_(
    NOT_DELETED,
    Transaction.amount < 0,
    row_category(IN_SYSTEM_GROUP),
    ON_CARD_ACCOUNT,
    not_(BALANCE_ADJUSTMENT_ROW),
)


# ─── Tags on the row's category or payee ─────────────────────────────────────
#
# Both are guarded by the NOT NULL test: `NULL IN (...)` is UNKNOWN, not FALSE,
# and a CASE arm evaluating to UNKNOWN differs from one evaluating FALSE only
# by luck of ordering. Keep every arm two-valued. `category_tagged` is what
# the activity classifier reads for the savings and debt tags; it lived there
# as `_tagged` until the essentials report needed the same shape.


def _tag_ids(system_keys: tuple[str, ...]):
    return select(Tag.id).where(
        Tag.system_key.in_(system_keys),
        Tag.is_deleted == False,  # noqa: E712
    )


def category_tagged(*system_keys: str):
    """Rows whose category carries any of these system tags."""
    return and_(
        Transaction.category_id.isnot(None),
        Transaction.category_id.in_(
            select(category_tags.c.category_id).where(
                category_tags.c.tag_id.in_(_tag_ids(system_keys))
            )
        ),
    )


def payee_tagged(*system_keys: str):
    """Rows whose payee carries any of these system tags."""
    return and_(
        Transaction.payee_id.isnot(None),
        Transaction.payee_id.in_(
            select(payee_tags.c.payee_id).where(payee_tags.c.tag_id.in_(_tag_ids(system_keys)))
        ),
    )


#: Spending the household could not do without: the category OR the payee is
#: tagged Essential. Evaluated only by TransactionRepository.essential_spend*
#: — the Guide, the Overview card and the Essentials report all read those.
ESSENTIAL_TAGGED = or_(category_tagged("essential"), payee_tagged("essential"))


#: A row that spends planned money: what plan-vs-actual reports may count as
#: "spent" against what `BUDGETED_ENVELOPE` counts as "assigned".
#:
#: This predicate existed twice — byte-identical, in `cumulative_variance` and
#: `budget_vs_actual` — and both copies were missing the same three terms, so
#: each subtracted a bigger spending universe from a smaller planning one:
#:
#: - `ON_BUDGET_ACCOUNT`: categorized rows on tracking accounts counted as
#:   spent; nothing is ever assigned against a tracking account.
#: - `row_category(SPENT_ENVELOPE)`: rows filed into system-group categories
#:   counted as spent while `BUDGETED_ENVELOPE` excludes them from assigned.
#:   Deleted categories stay IN, exactly as `SPENT_ENVELOPE` documents — the
#:   money moved, and deleting the envelope afterwards does not unspend it.
#:   The EXISTS also absorbs `category_id IS NOT NULL`: a NULL category
#:   matches no Category row.
#: - The activity-class filter, which cannot live here: callers add
#:   `_spending_classes()` AND `apply_class_joins`, because the predicate and
#:   the joins must travel together (see `_spending_classes`' docstring — a
#:   query with the class filter and no joins is a cartesian product).
#:   Without it, a categorized brokerage transfer (SAVINGS) or a mortgage
#:   principal payment (DEBT_PRINCIPAL) counted as spending with no matching
#:   assignment, and cumulative variance compounded the gap every month.
#:
#: One divergence is deliberate and stays: `amount < 0` means a refund posted
#: to a spending category never reduces "spent". Pinned by test rather than
#: silently changed — flipping it would move every historical variance figure.
PLANNED_SPEND_ROW = and_(
    NOT_DELETED,
    POSTED,
    Transaction.amount < 0,
    LEAF,
    CASH_FLOW_ROW,
    ON_BUDGET_ACCOUNT,
    row_category(SPENT_ENVELOPE),
)
