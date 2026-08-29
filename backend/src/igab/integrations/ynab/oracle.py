"""What YNAB's own export says Ready to Assign should be — pure.

A YNAB export carries YNAB's answers: every inflow, every assignment, and each
category's month-end Available. Nothing here touches the database; the
importer's parity check and the `ynab-oracle` script both read this so the
figure the import summary compares against is computed exactly one way.

The rules, validated to the cent against a real cash-only export:

    inflow      = Σ register rows (and split legs) filed "Inflow: Ready to
                  Assign", dated on or before the month's end, on accounts
                  in scope
    assigned    = Σ Plan Assigned over EVERY month — YNAB deducts future
                  months from today's figure too
    written off = for each (category, earlier month) that ended negative,
                  the part of the overspending NOT spent on a credit card:
                  YNAB takes cash overspending out of Ready to Assign at the
                  month boundary and lets credit overspending ride on the
                  card as unfunded debt
    rta         = inflow − assigned − written off

IGAB has no card-payment reserves: a card is an on-budget account whose
balance nets against cash, and the importer skips YNAB's "Credit Card
Payments" group. So once a month in which a category was overspent on a card
has been reset, IGAB's Ready to Assign sits below YNAB's by the debt YNAB
parked unfunded on the card:

    uncovered (total)   = −card balances − card-payment reserves available
    uncovered (current) = Σ over categories negative THIS month of
                          min(overspent, card outflows in it this month)
                          — still visible as negatives, so not yet a gap
    expected_igab       = rta − (uncovered total − uncovered current)

And an uncategorized row on a budget account is money YNAB leaves out of the
plan entirely until it is filed, while IGAB takes it out of Ready to Assign
at once (a reconciliation adjustment is exactly such a row, on purpose):

    expected_igab       = rta − (uncovered total − uncovered current)
                          + uncategorized net on budget accounts

Within a month with no card overspending on the books and every row filed,
the two agree exactly.

One more thing the export cannot say outright: YNAB counts an imported
transaction in the plan only once it is approved, but ships it in the
register either way, and the register carries no approved flag — only a
cleared state, and an unapproved row is always uncleared (not the reverse:
a hand-entered row is uncleared and counted). So each envelope's uncleared
rows in the compared month are reported beside its Available; a difference
equal to the sum of some of them is YNAB waiting for approvals, not a
disagreement. (Ready to Assign is unaffected: such a row moves the balance
and the envelope by the same amount.)
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from igab.domain.dates import month_end, month_start
from igab.integrations.ynab.models import YNABBudget, YNABPlanRow

ZERO = Decimal("0")
_INFLOW = ("Inflow", "Ready to Assign")
_CREDIT_CARD_PAYMENTS = "Credit Card Payments"


@dataclass
class RTAOracle:
    month: date
    inflow: Decimal
    assigned: Decimal
    credit_card_payment_assigned: Decimal
    cash_overspending_written_off: Decimal
    #: YNAB's Ready to Assign for `month`.
    rta: Decimal
    card_balances: Decimal
    ccp_available: Decimal
    uncovered_current: Decimal
    #: Card debt YNAB has reset out of the envelopes but not charged to
    #: Ready to Assign — the one difference from IGAB's figure by construction.
    uncovered_card_debt: Decimal
    #: Net of uncategorized, non-transfer rows on budget accounts through the
    #: month — out of Ready to Assign in IGAB, out of the plan in YNAB.
    uncategorized_net: Decimal
    expected_igab: Decimal
    #: YNAB's Available per envelope category at `month`, keyed by IGAB's
    #: (group, category) names; the card-payment group is left out.
    available: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    #: The uncleared rows per envelope in `month`, same keys — the ones YNAB
    #: may still be waiting to approve.
    uncleared: dict[tuple[str, str], list[Decimal]] = field(default_factory=dict)


def ynab_rta(
    budget: YNABBudget,
    month: date,
    *,
    accounts: Collection[str] | None = None,
    credit_card_accounts: Collection[str] = (),
    tracking_accounts: Collection[str] = (),
) -> RTAOracle:
    """See the module docstring. `accounts` limits the register to the
    accounts that were imported (a skipped account's rows never reach IGAB);
    None means all of them. Closed accounts stay in scope — closing moves no
    money. `tracking_accounts` are the off-budget ones: their uncategorized
    rows are net-worth movement, not money out of Ready to Assign. Names
    compare case-insensitively, as the importer does."""
    # Imported lazily by name to keep this module free of importer state;
    # it is the importer's one mapping of YNAB's names to IGAB's.
    from igab.integrations.ynab.importer import _TRANSFER_PREFIX, map_ynab_names

    month = month_start(month)
    end = month_end(month)
    in_scope = None if accounts is None else {a.lower() for a in accounts}
    cards = {a.lower() for a in credit_card_accounts}
    tracking = {a.lower() for a in tracking_accounts}

    def kept(account_name: str) -> bool:
        return in_scope is None or account_name.lower() in in_scope

    inflow = ZERO
    card_balances = ZERO
    uncategorized_net = ZERO
    # (group, category, month) → outflow on credit cards, as a positive figure
    card_outflows: dict[tuple[str, str, date], Decimal] = defaultdict(lambda: ZERO)
    uncleared: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for txn in budget.transactions:
        if not kept(txn.account_name) or txn.date > end:
            continue
        on_card = txn.account_name.lower() in cards
        if on_card:
            card_balances += txn.amount
        on_budget = txn.account_name.lower() not in tracking
        is_transfer = txn.payee.startswith(_TRANSFER_PREFIX)
        in_month = txn.date >= month
        legs = txn.splits or [txn]
        for leg in legs:
            key = (leg.category_group, leg.category)
            if key == _INFLOW:
                inflow += leg.amount
            if not (leg.category_group and leg.category):
                if on_budget and not is_transfer:
                    uncategorized_net += leg.amount
                continue
            if on_card and leg.amount < 0:
                card_outflows[
                    (leg.category_group, leg.category, month_start(txn.date))
                ] += -leg.amount
            if in_month and txn.cleared == "uncleared":
                uncleared[map_ynab_names(leg.category_group, leg.category)].append(leg.amount)

    assigned = ZERO
    ccp_assigned = ZERO
    written_off = ZERO
    uncovered_current = ZERO
    ccp_available = ZERO
    available: dict[tuple[str, str], Decimal] = {}
    for row in budget.plan_rows:
        assigned += row.assigned
        is_ccp = row.category_group == _CREDIT_CARD_PAYMENTS
        if is_ccp:
            ccp_assigned += row.assigned
        if row.available is None:
            continue
        if row.month < month and row.available < 0:
            overspent = -row.available
            on_card = card_outflows.get((row.category_group, row.category, row.month), ZERO)
            written_off += max(ZERO, overspent - on_card)
        if row.month == month:
            if is_ccp:
                ccp_available += row.available
            else:
                available[map_ynab_names(row.category_group, row.category)] = row.available
                if row.available < 0:
                    on_card = card_outflows.get((row.category_group, row.category, row.month), ZERO)
                    uncovered_current += min(-row.available, on_card)

    rta = inflow - assigned - written_off
    uncovered_total = -card_balances - ccp_available
    uncovered_card_debt = uncovered_total - uncovered_current
    return RTAOracle(
        month=month,
        inflow=inflow,
        assigned=assigned,
        credit_card_payment_assigned=ccp_assigned,
        cash_overspending_written_off=written_off,
        rta=rta,
        card_balances=card_balances,
        ccp_available=ccp_available,
        uncovered_current=uncovered_current,
        uncovered_card_debt=uncovered_card_debt,
        uncategorized_net=uncategorized_net,
        expected_igab=rta - uncovered_card_debt + uncategorized_net,
        available=available,
        uncleared={k: v for k, v in uncleared.items() if k in available},
    )


def subset_sums(amounts: list[Decimal], limit: int = 16) -> set[Decimal]:
    """Every total some non-empty subset of `amounts` adds up to. Past
    `limit` rows only the full total is offered — a month with that many
    uncleared rows in one envelope is a review queue, not an approval."""
    if len(amounts) > limit:
        return {sum(amounts, ZERO)}
    sums: set[Decimal] = set()
    for amount in amounts:
        sums |= {s + amount for s in sums} | {amount}
    return sums


#: A file whose own numbers disagree with each other more than this is not a
#: faithful export — anonymised, hand-edited, or assembled from two different
#: points in time. The gate asks "is this file coherent at all", not "is it
#: precise": a real export sits at zero, and the files this catches sit above
#: a third. Anything in between should be looked at by a person either way.
INCOHERENT_FRACTION = Decimal("0.05")


@dataclass
class ExportConsistency:
    """Does the export agree with itself?

    Parity compares IGAB's recomputed Available against the Available column
    YNAB shipped. That comparison only means anything if the file's own
    numbers hang together, and two invariants say whether they do:

    carryover   Available == prior Available + Assigned + Activity, down each
                category's months. YNAB's cash-overspending write-off (a
                negative month-end that starts the next month at zero) counts
                as holding, as does credit overspending riding forward.
    activity    each Plan Activity cell equals the register rows filed to that
                category in that month. This is the one that decides parity:
                IGAB's balance is built from the register, so where the two
                disagree the comparison is measuring the file, not IGAB.

    Both are properties of the file alone — no import choices, no database.
    """

    carryover_rows_checked: int
    carryover_rows_violating: int
    activity_cells_checked: int
    activity_cells_disagreeing: int

    @property
    def carryover_violation_rate(self) -> Decimal:
        return _rate(self.carryover_rows_violating, self.carryover_rows_checked)

    @property
    def activity_disagreement_rate(self) -> Decimal:
        return _rate(self.activity_cells_disagreeing, self.activity_cells_checked)

    @property
    def self_consistent(self) -> bool:
        """False only on evidence. A register-only export checks nothing and
        is not thereby suspect — both rates are zero and it passes."""
        return (
            self.carryover_violation_rate <= INCOHERENT_FRACTION
            and self.activity_disagreement_rate <= INCOHERENT_FRACTION
        )


def _rate(part: int, whole: int) -> Decimal:
    return ZERO if whole == 0 else Decimal(part) / Decimal(whole)


def export_consistency(budget: YNABBudget) -> ExportConsistency:
    """See `ExportConsistency`. Every account is in scope: the plan reflects
    the whole budget, so skipping an account at import does not make the file
    disagree with itself."""
    plan_rows = [r for r in budget.plan_rows if r.category_group != _CREDIT_CARD_PAYMENTS]

    # --- carryover: Available == prior Available + Assigned + Activity ---
    by_category: dict[tuple[str, str], list[YNABPlanRow]] = defaultdict(list)
    for row in plan_rows:
        by_category[(row.category_group, row.category)].append(row)

    carryover_checked = 0
    carryover_violating = 0
    for rows in by_category.values():
        previous: Decimal | None = None
        for row in sorted(rows, key=lambda r: r.month):
            if row.available is None or row.activity is None:
                previous = row.available
                continue
            # The earliest month has nothing to carry from, so it seeds the
            # walk rather than being checked against an assumed zero.
            if previous is not None:
                carryover_checked += 1
                expected = previous + row.assigned + row.activity
                # Overspending either rides forward on the card (available ==
                # expected) or comes out of Ready to Assign at the boundary
                # (available == 0). Both are YNAB behaving.
                if row.available != expected and not (expected < ZERO and row.available == ZERO):
                    carryover_violating += 1
            previous = row.available

    # --- activity: the Plan's Activity vs the register shipped beside it ---
    register_net: dict[tuple[str, str, date], Decimal] = defaultdict(lambda: ZERO)
    for txn in budget.transactions:
        for leg in txn.splits or [txn]:
            if not (leg.category_group and leg.category):
                continue
            register_net[(leg.category_group, leg.category, month_start(txn.date))] += leg.amount

    activity_checked = 0
    activity_disagreeing = 0
    for row in plan_rows:
        if row.activity is None:
            continue
        activity_checked += 1
        key = (row.category_group, row.category, row.month)
        if row.activity != register_net.get(key, ZERO):
            activity_disagreeing += 1

    return ExportConsistency(
        carryover_rows_checked=carryover_checked,
        carryover_rows_violating=carryover_violating,
        activity_cells_checked=activity_checked,
        activity_cells_disagreeing=activity_disagreeing,
    )
