"""Does the budget IGAB just built agree with the export it was built from?

Runs once, right after an import, and puts the answer in the summary the
user reads: YNAB's own Ready to Assign (from the file), the figure IGAB's
arithmetic should reach (adjusted only for unfiled cash rows), the
figure it did reach, and how many envelope balances differ from the
Available column YNAB shipped. A number that has to be trusted should be
checked where the evidence is, not explained later.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from igab.domain.dates import add_months
from igab.domain.money import quantize_cents
from igab.integrations.ynab.models import YNABBudget
from igab.integrations.ynab.oracle import (
    ExportConsistency,
    anchored_expected,
    ccp_available_history,
    export_consistency,
    subset_sums,
    ynab_rta,
)
from igab.repositories.category_repo import CategoryRepository
from igab.services.budget_service import BudgetService


@dataclass
class ParityDifference:
    name: str
    igab: Decimal
    ynab: Decimal
    #: Uncleared rows of the envelope this month that add up to exactly this
    #: difference — YNAB waiting on their approval, not a disagreement: the
    #: register ships such rows, the plan counts them once approved. Zero
    #: when no such rows do.
    pending: Decimal = Decimal("0")
    #: A card inflow filed here that repaid uncovered debt. A stated, bounded
    #: divergence, not a defect: YNAB releases a card refund from the CCP
    #: reserve uncapped and hands the whole thing back to the envelope, so its
    #: Available is higher by exactly this. IGAB routes the part that met debt
    #: nobody had reserved cash for to the card instead, because no cash
    #: arrived and the envelope cannot spend it. The two still agree on Ready
    #: to Assign — the errors cancel in YNAB's ledger — which is why this shows
    #: up here and nowhere else.
    repaid_uncovered_debt: Decimal = Decimal("0")

    @property
    def explained(self) -> bool:
        gap = quantize_cents(self.igab - self.ynab)
        return (self.pending != 0 and gap == quantize_cents(self.pending)) or (
            self.repaid_uncovered_debt != 0 and gap == quantize_cents(-self.repaid_uncovered_debt)
        )


@dataclass
class CardHistoryDivergence:
    """The first month a card's set-aside detached from YNAB's reserve.

    The single-month `card_differences` says a card is off TODAY; on a
    ten-year import the actionable fact is WHEN it started — the register of
    that one month is a few dozen rows, the register of ten years is not.
    Only cards with at least one divergent month get an entry."""

    name: str
    first_month: date
    #: The two figures at `first_month`, so the entry says how far apart
    #: they started, not just that they did.
    igab: Decimal
    ynab: Decimal
    months_compared: int
    months_differing: int


@dataclass
class ParityReport:
    month: date
    ynab_ready_to_assign: Decimal
    expected_ready_to_assign: Decimal
    igab_ready_to_assign: Decimal
    uncovered_card_debt: Decimal
    #: Uncategorized rows on budget accounts — out of Ready to Assign here,
    #: out of the plan in YNAB until filed.
    uncategorized_net: Decimal
    #: Ready to Assign as expected AND no unexplained envelope difference.
    matches: bool
    categories_compared: int
    #: Envelopes that differ by something other than their pending rows.
    categories_differing: int
    #: Envelopes that differ by exactly their uncleared rows this month.
    categories_pending: int
    #: Envelopes YNAB priced that no IGAB category answered to — a name or
    #: casing the importer stored differently. They are not compared, and
    #: without this they would leave no trace but a smaller `compared`.
    categories_unmatched: int
    top_differences: list[ParityDifference]
    #: Card set-asides held against the Credit Card Payments reserve YNAB
    #: shipped for the same card. Both sides simulate the same rules over
    #: the same history, so a card that fails here is a card whose envelope
    #: has detached from its ledger — exactly the drift "The Unreleased
    #: Reservation" accumulated silently across an entire import. An import
    #: is the one moment this is severe and the user has no baseline to
    #: notice it against, so it is checked where the evidence is.
    cards_compared: int
    cards_differing: int
    card_differences: list[ParityDifference]
    #: Per card, the first month IGAB's set-aside and YNAB's CCP Available
    #: disagreed — every month of the plan is compared, not just the viewed
    #: one. Known-model divergences (a card refund repaying uncovered debt —
    #: see `ParityDifference.repaid_uncovered_debt`) appear here too; the
    #: entry names where the gap opened, which is where to read the register.
    card_history: list[CardHistoryDivergence]
    #: YNAB's shipped CCP Available, per card (lowercased name) per plan
    #: month — the series `card_history` was measured against, carried whole.
    #: The import route persists it with the summary because the export zip
    #: is the only other place it exists, and a reserve question usually
    #: arrives after the zip is gone (scripts/card_reserve_probe.py reads it
    #: back for its YNAB overlay).
    ccp_available_history: dict[str, dict[date, Decimal]]
    #: Whether the export's own numbers agree with each other. When they do
    #: not, `categories_differing` measures the file, not the import.
    consistency: ExportConsistency


async def check_parity(
    budget_service: BudgetService,
    category_repo: CategoryRepository,
    budget_id: uuid.UUID,
    ynab_budget: YNABBudget,
    month: date,
    *,
    accounts: Collection[str] | None,
    credit_card_accounts: Collection[str],
    tracking_accounts: Collection[str] = (),
    max_differences: int = 5,
    anchor: date | None = None,
) -> ParityReport:
    oracle = ynab_rta(
        ynab_budget,
        month,
        accounts=accounts,
        credit_card_accounts=credit_card_accounts,
        tracking_accounts=tracking_accounts,
    )
    summary = await budget_service.get_budget_summary(budget_id, month)
    balances = {b.category_id: b for b in summary.category_balances if not b.in_system_group}
    rows = await category_repo.get_all_with_group_names(budget_id, include_archived=True)
    by_name = {(group_name, category.name): category.id for category, group_name in rows}

    differences: list[ParityDifference] = []
    compared = 0
    unmatched = 0
    for (group, name), theirs in oracle.available.items():
        category_id = by_name.get((group, name))
        balance = balances.get(category_id) if category_id is not None else None
        if balance is None:
            unmatched += 1
            continue
        compared += 1
        if quantize_cents(balance.available) != quantize_cents(theirs):
            gap = quantize_cents(balance.available - theirs)
            candidates = {
                quantize_cents(s) for s in subset_sums(oracle.uncleared.get((group, name), []))
            }
            differences.append(
                ParityDifference(
                    f"{group}: {name}",
                    balance.available,
                    theirs,
                    pending=gap if gap in candidates else Decimal("0"),
                    repaid_uncovered_debt=balance.repaid_uncovered_debt,
                )
            )
    unexplained = [d for d in differences if not d.explained]
    unexplained.sort(key=lambda d: abs(d.igab - d.ynab), reverse=True)

    # Cards: IGAB's simulated set-aside against the CCP Available YNAB
    # shipped for the same card (named after the card, matched the way the
    # importer matched it). Only cards the export priced are compared — a
    # card created outside the import has no YNAB answer to check against.
    card_differences: list[ParityDifference] = []
    cards_compared = 0
    for card in summary.cards:
        theirs = oracle.ccp_available_by_card.get(card.name.lower())
        if theirs is None:
            continue
        cards_compared += 1
        if quantize_cents(card.set_aside) != quantize_cents(theirs):
            card_differences.append(ParityDifference(card.name, card.set_aside, theirs))
    card_differences.sort(key=lambda d: abs(d.igab - d.ynab), reverse=True)

    # Every month of every card, against the file's own series — one walk
    # (`card_reserves`), not one summary per month. `set_aside` evaluates at
    # any month, so ten years costs no more than one.
    history = ccp_available_history(ynab_budget)
    card_history: list[CardHistoryDivergence] = []
    reserves = await budget_service.card_reserves(budget_id, month)
    for _account_id, (name, reserve) in reserves.items():
        series = history.get(name.lower())
        if not series:
            continue
        # On an anchored budget the comparison starts at B−1: earlier
        # months were never re-derived, and B−1 itself is free — the reserve
        # there IS the anchor row, so comparing it asserts the seeds
        # round-tripped the file exactly.
        floor_month = add_months(anchor, -1) if anchor is not None else None
        months = [
            m
            for m in sorted(series)
            if m <= oracle.month and (floor_month is None or m >= floor_month)
        ]
        divergent = [
            m for m in months if quantize_cents(reserve.set_aside(m)) != quantize_cents(series[m])
        ]
        if divergent:
            first = divergent[0]
            card_history.append(
                CardHistoryDivergence(
                    name=name,
                    first_month=first,
                    igab=quantize_cents(reserve.set_aside(first)),
                    ynab=quantize_cents(series[first]),
                    months_compared=len(months),
                    months_differing=len(divergent),
                )
            )
    card_history.sort(key=lambda d: d.first_month)

    igab = summary.to_be_assigned
    # Anchored budgets are held to the cash form: every term is the file's
    # own displayed position, so the handoff must match even when the file's
    # month-by-month history contradicts itself. The history form (`rta`)
    # stays what "YNAB's own figures" reports — it is still YNAB's number.
    expected = anchored_expected(oracle) if anchor is not None else oracle.expected_igab
    return ParityReport(
        month=oracle.month,
        ynab_ready_to_assign=quantize_cents(oracle.rta),
        expected_ready_to_assign=quantize_cents(expected),
        igab_ready_to_assign=quantize_cents(igab),
        uncovered_card_debt=quantize_cents(oracle.uncovered_card_debt),
        uncategorized_net=quantize_cents(oracle.uncategorized_net),
        matches=quantize_cents(igab) == quantize_cents(expected)
        and not unexplained
        and not card_differences,
        categories_compared=compared,
        categories_differing=len(unexplained),
        categories_pending=len(differences) - len(unexplained),
        categories_unmatched=unmatched,
        top_differences=unexplained[:max_differences],
        cards_compared=cards_compared,
        cards_differing=len(card_differences),
        card_differences=card_differences[:max_differences],
        card_history=card_history[:max_differences],
        ccp_available_history=history,
        consistency=export_consistency(ynab_budget),
    )
