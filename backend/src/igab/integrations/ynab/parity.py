"""Does the budget IGAB just built agree with the export it was built from?

Runs once, right after an import, and puts the answer in the summary the
user reads: YNAB's own Ready to Assign (from the file), the figure IGAB's
arithmetic should reach given the one difference it makes on purpose, the
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

from igab.domain.money import quantize_cents
from igab.integrations.ynab.models import YNABBudget
from igab.integrations.ynab.oracle import subset_sums, ynab_rta
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

    @property
    def explained(self) -> bool:
        return self.pending != 0 and quantize_cents(self.igab - self.ynab) == quantize_cents(
            self.pending
        )


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
    top_differences: list[ParityDifference]


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
    rows = await category_repo.get_all_with_group_names(budget_id, include_hidden=True)
    by_name = {(group_name, category.name): category.id for category, group_name in rows}

    differences: list[ParityDifference] = []
    compared = 0
    for (group, name), theirs in oracle.available.items():
        category_id = by_name.get((group, name))
        balance = balances.get(category_id) if category_id is not None else None
        if balance is None:
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
                )
            )
    unexplained = [d for d in differences if not d.explained]
    unexplained.sort(key=lambda d: abs(d.igab - d.ynab), reverse=True)

    igab = summary.to_be_assigned
    return ParityReport(
        month=oracle.month,
        ynab_ready_to_assign=quantize_cents(oracle.rta),
        expected_ready_to_assign=quantize_cents(oracle.expected_igab),
        igab_ready_to_assign=quantize_cents(igab),
        uncovered_card_debt=quantize_cents(oracle.uncovered_card_debt),
        uncategorized_net=quantize_cents(oracle.uncategorized_net),
        matches=quantize_cents(igab) == quantize_cents(oracle.expected_igab) and not unexplained,
        categories_compared=compared,
        categories_differing=len(unexplained),
        categories_pending=len(differences) - len(unexplained),
        top_differences=unexplained[:max_differences],
    )
