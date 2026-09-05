"""A budget as a readable, portable export — the other half of a snapshot.

A snapshot is exact and machine-shaped: every table, every id, meant to be read
back by this app alone. This is the file you open in a spreadsheet, hand to
someone, or feed into another tool. It is deliberately lossy, and it says so
in writing inside the file.

**The shape is YNAB's, and that is the point.** ``YNABParser.parse_zip``
already reads it — transfers as a ``Transfer : <Account>`` payee, splits
flattened with a ``Split (n/m)`` marker, cleared state per row — so exporting
in this shape costs no new import code at all: ``POST /budgets/import-ynab``
reads IGAB's own export unchanged.

Two rules hold this together, and both are the same rule:

- **The plan is not recomputed here.** ``Plan.csv`` is
  ``BudgetService.get_budget_summary`` looped over the budget's months.
  ``CategoryBalance`` already carries exactly assigned / activity / available.
  A second implementation of budget math is the last thing this app needs.
- **Money and dates are written by the inverses of the readers**
  (``domain.money.format_csv_amount``, ``integrations.ynab.writer``), never by
  an f-string at a call site.
"""

import json
import zipfile
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any, BinaryIO
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Base
from igab.domain.exceptions import NotFoundError
from igab.domain.money import format_csv_amount
from igab.integrations.ynab.writer import (
    ACCOUNT_COLUMNS,
    PLAN_COLUMNS,
    REGISTER_COLUMNS,
    format_cleared,
    format_date,
    format_month,
    group_category,
    split_memo,
    transfer_payee,
    write_csv,
)
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.import_anchor_repo import ImportAnchorRepository
from igab.services.budget_service import BudgetService

ZERO = Decimal("0")

#: Named in the file, because a lossy export that does not say what it dropped
#: is exactly the failure this repository keeps writing rules about. Each of
#: these is in a snapshot; the snapshot is the answer for anyone who needs
#: them.
NOT_CARRIED: dict[str, str] = {
    "Attachments": "Receipt images and PDFs.",
    "Undo history": "The change log, and the ability to undo anything in it.",
    "Views and filters": "Saved budget views and saved register filters.",
    "Reconciliation history": "Statement balances from past reconciliations.",
    "AI history": "Queued and completed AI jobs.",
    "Guide and wishlist": "Roadmap answers, bindings, and wishlist items.",
    "Approval state": "Whether a transaction had been reviewed.",
    "Pre-anchor plan history": (
        "Envelope balances and assignments from months before the import "
        "anchor — the anchor month's row is the boundary statement; every "
        "transaction is still in the register."
    ),
}


def _safe_member(name: str) -> str:
    """A budget name that is safe as a zip member name."""
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip()
    return cleaned or "Budget"


async def _budget(session: AsyncSession, budget_id: UUID) -> Any:
    budgets = Base.metadata.tables["budgets"]
    row = (
        await session.execute(
            select(budgets.c.id, budgets.c.name, budgets.c.currency_code).where(
                budgets.c.id == budget_id
            )
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("budget", str(budget_id))
    return row


async def _month_range(session: AsyncSession, budget_id: UUID) -> list[date]:
    """Every month the budget has anything to say about, first to last.

    From transactions and assignments together: a month that was funded and
    never spent is still part of the plan, and a month with spending and no
    assignment obviously is.
    """
    transactions = Base.metadata.tables["transactions"]
    assignments = Base.metadata.tables["budget_assignments"]

    bounds = (
        await session.execute(
            select(func.min(transactions.c.date), func.max(transactions.c.date)).where(
                transactions.c.budget_id == budget_id,
                transactions.c.is_deleted.is_(False),
            )
        )
    ).one()
    assigned = (
        await session.execute(
            select(func.min(assignments.c.month), func.max(assignments.c.month)).where(
                assignments.c.budget_id == budget_id
            )
        )
    ).one()

    starts = [d for d in (bounds[0], assigned[0]) if d is not None]
    ends = [d for d in (bounds[1], assigned[1]) if d is not None]
    if not starts or not ends:
        return []

    first = min(starts).replace(day=1)
    # An anchored budget's plan starts at its anchor's B−1: the summary loop
    # below would otherwise export pre-anchor months the walks never derive.
    # B−1 itself IS exported — its rows carry the openings as Available, an
    # opening-statement month — so re-importing this file re-anchors at the
    # same boundary and reads the same openings back.
    # Through the repository, which is the ONE assembler of a budget's anchor.
    # This used to read `min(month)` directly — a second answer to "what month
    # is this budget anchored at", and one that silently picked the earliest
    # where `_assemble` refuses to pick at all. Two answers to that question
    # cannot both be right about a budget whose rows disagree.
    anchor = await ImportAnchorRepository(session).get_for_budget(budget_id)
    if anchor is not None:
        first = max(first, anchor.openings.opening_month)
    last = max(ends).replace(day=1)
    months: list[date] = []
    cursor = first
    while cursor <= last:
        months.append(cursor)
        cursor = (
            date(cursor.year + 1, 1, 1)
            if cursor.month == 12
            else date(cursor.year, cursor.month + 1, 1)
        )
    return months


async def _register_rows(session: AsyncSession, budget_id: UUID) -> list[dict[str, str]]:
    """The register, in the order the parser needs to read it back.

    Split legs must come out consecutively and in order — ``_reassemble_splits``
    groups a run of ``(1/n)…(n/n)`` sharing account, date, payee and cleared
    state, and falls back to flat rows for anything irregular. So a parent is
    replaced in place by its children rather than each being emitted wherever
    its own id happens to sort.
    """
    transactions = Base.metadata.tables["transactions"]
    accounts = Base.metadata.tables["accounts"]
    payees = Base.metadata.tables["payees"]
    categories = Base.metadata.tables["categories"]
    groups = Base.metadata.tables["category_groups"]

    query = (
        select(
            transactions.c.id,
            transactions.c.date,
            transactions.c.amount,
            transactions.c.memo,
            transactions.c.cleared,
            transactions.c.is_split,
            transactions.c.parent_transaction_id,
            transactions.c.transfer_id,
            transactions.c.account_id,
            accounts.c.name.label("account_name"),
            payees.c.name.label("payee_name"),
            categories.c.name.label("category_name"),
            groups.c.name.label("group_name"),
        )
        .select_from(
            transactions.join(accounts, accounts.c.id == transactions.c.account_id)
            .outerjoin(payees, payees.c.id == transactions.c.payee_id)
            .outerjoin(categories, categories.c.id == transactions.c.category_id)
            .outerjoin(groups, groups.c.id == categories.c.category_group_id)
        )
        .where(transactions.c.budget_id == budget_id, transactions.c.is_deleted.is_(False))
        .order_by(transactions.c.date, transactions.c.id)
    )
    rows = [dict(row) for row in (await session.execute(query)).mappings()]

    by_id = {row["id"]: row for row in rows}
    children: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows:
        parent = row["parent_transaction_id"]
        if parent is not None:
            children.setdefault(parent, []).append(row)

    out: list[dict[str, str]] = []
    for row in rows:
        if row["parent_transaction_id"] is not None:
            continue  # emitted with its parent, below
        legs = children.get(row["id"], [])
        if row["is_split"] and legs:
            total = len(legs)
            for index, leg in enumerate(legs, start=1):
                out.append(
                    _register_row(
                        leg,
                        by_id,
                        payee=_payee_for(row, by_id),
                        memo=split_memo(index, total, leg["memo"]),
                        cleared=row["cleared"],
                    )
                )
        else:
            out.append(_register_row(row, by_id, payee=_payee_for(row, by_id), memo=row["memo"]))
    return out


def _payee_for(row: dict[str, Any], by_id: dict[UUID, dict[str, Any]]) -> str:
    """A transfer names the other account; everything else names its payee."""
    partner_id = row.get("transfer_id")
    if partner_id is not None:
        partner = by_id.get(partner_id)
        if partner is not None:
            return transfer_payee(str(partner["account_name"]))
    return str(row.get("payee_name") or "")


def _register_row(
    row: dict[str, Any],
    by_id: dict[UUID, dict[str, Any]],
    *,
    payee: str,
    memo: str | None,
    cleared: str | None = None,
) -> dict[str, str]:
    amount: Decimal = row["amount"]
    group = row.get("group_name")
    category = row.get("category_name")
    return {
        "Account": str(row["account_name"]),
        "Flag": "",
        "Date": format_date(row["date"]),
        "Payee": payee,
        "Category Group/Category": group_category(group, category),
        "Category Group": group or "",
        "Category": category or "",
        "Memo": memo or "",
        # YNAB splits the sign across two columns; the parser reads
        # inflow - outflow back into one amount.
        "Outflow": format_csv_amount(-amount) if amount < ZERO else "",
        "Inflow": format_csv_amount(amount) if amount >= ZERO else "",
        "Cleared": format_cleared(cleared or row["cleared"]),
    }


async def _plan_rows(
    budget_service: BudgetService,
    category_repo: CategoryRepository,
    budget_id: UUID,
    months: list[date],
) -> Iterator[dict[str, str]]:
    """One row per (category, month), straight from the budget summary."""
    named = await category_repo.get_all_with_group_names(budget_id, include_archived=True)
    names = {category.id: (group_name, category.name) for category, group_name in named}

    rows: list[dict[str, str]] = []
    for month in months:
        summary = await budget_service.get_budget_summary(budget_id, month)
        for balance in summary.category_balances:
            name = names.get(balance.category_id)
            if name is None:
                continue
            group, category = name
            rows.append(
                {
                    "Month": format_month(month),
                    "Category Group/Category": group_category(group, category),
                    "Category Group": group,
                    "Category": category,
                    # Income categories: the app itself blanks these, because a
                    # lifetime income total under a "free to assign" hero is a
                    # lie. The export shows what the app shows.
                    "Assigned": ""
                    if balance.in_system_group
                    else format_csv_amount(balance.assigned),
                    # A card-payment envelope's activity is a computed
                    # set-aside, not rows filed to it — the register shows a
                    # card payment as a transfer. This column means "the
                    # register rows filed to this category this month", so
                    # writing IGAB's figure here would be a false claim, and
                    # writing zero would be a different false claim. Blank
                    # says what is true: the number is not that number.
                    # (YNAB has the same problem and solves it by naming the
                    # group "Credit Card Payments"; IGAB's envelope lives in
                    # whichever group the user put it in.)
                    "Activity": ""
                    if balance.is_card_payment
                    else format_csv_amount(balance.activity),
                    "Available": ""
                    if balance.in_system_group
                    else format_csv_amount(balance.available),
                }
            )
    return iter(rows)


async def _account_rows(session: AsyncSession, budget_id: UUID) -> list[dict[str, str]]:
    """The real account types, so a re-import is two clicks rather than a
    re-mapping chore — ``build_ynab_preview`` guesses types from names when
    this member is absent."""
    accounts = Base.metadata.tables["accounts"]
    query = (
        select(
            accounts.c.name,
            accounts.c.account_type,
            accounts.c.classification,
            accounts.c.on_budget,
            accounts.c.is_closed,
            accounts.c.note,
        )
        .where(accounts.c.budget_id == budget_id, accounts.c.is_deleted.is_(False))
        .order_by(accounts.c.sort_order, accounts.c.name)
    )
    return [
        {
            "Account": row.name,
            "Type": row.account_type,
            "Classification": row.classification,
            "On Budget": "true" if row.on_budget else "false",
            "Closed": "true" if row.is_closed else "false",
            "Note": row.note or "",
        }
        for row in (await session.execute(query)).all()
    ]


def _readme(budget_name: str, months: list[date]) -> str:
    span = (
        f"{format_month(months[0])} to {format_month(months[-1])}"
        if months
        else "no months of activity yet"
    )
    dropped = "\n".join(f"  - {name}: {why}" for name, why in NOT_CARRIED.items())
    return (
        f'IGAB export of "{budget_name}" — {span}.\n'
        f"\n"
        f"This file is YNAB-shaped on purpose: the Register and Plan members\n"
        f"read in the format YNAB exports, so a spreadsheet opens them and\n"
        f"IGAB's own YNAB importer reads them back.\n"
        f"\n"
        f"WHAT IS NOT IN THIS FILE\n"
        f"{dropped}\n"
        f"\n"
        f"If you need any of the above, take a budget snapshot instead\n"
        f"(Settings -> Budget Backups). A snapshot is exact and lossless; this\n"
        f"export is readable and portable. They answer different questions.\n"
        f"\n"
        f"A credit card's payment envelope shows no Activity figure. What IGAB\n"
        f"holds there is money set aside to pay the card, not spending filed to\n"
        f"that category — the register shows a card payment as a transfer. Its\n"
        f"assigned and available figures are real and are included.\n"
        f"\n"
        f"Income categories show Activity only. IGAB blanks their assigned and\n"
        f"available figures on screen for the same reason: a lifetime income\n"
        f'total under a "free to assign" heading is not a fact about money you\n'
        f"can spend.\n"
    )


async def export_budget_ynab(
    session: AsyncSession,
    budget_service: BudgetService,
    category_repo: CategoryRepository,
    budget_id: UUID,
    out: BinaryIO,
    *,
    app_version: str,
    exported_at: str,
) -> dict[str, Any]:
    """Write the export into ``out`` and return what the manifest says."""
    budget = await _budget(session, budget_id)
    months = await _month_range(session, budget_id)
    member = _safe_member(budget.name)

    register = await _register_rows(session, budget_id)
    plan = list(await _plan_rows(budget_service, category_repo, budget_id, months))
    accounts = await _account_rows(session, budget_id)

    manifest = {
        "format": "igab.budget-export",
        "shape": "ynab",
        "app_version": app_version,
        "exported_at": exported_at,
        "budget_name": budget.name,
        "currency_code": budget.currency_code,
        "months": [format_month(m) for m in months],
        "row_counts": {
            "register": len(register),
            "plan": len(plan),
            "accounts": len(accounts),
        },
        "not_carried": NOT_CARRIED,
    }

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{member} - Register.csv", write_csv(REGISTER_COLUMNS, register))
        archive.writestr(f"{member} - Plan.csv", write_csv(PLAN_COLUMNS, plan))
        archive.writestr("Accounts.csv", write_csv(ACCOUNT_COLUMNS, accounts))
        archive.writestr("README.txt", _readme(budget.name, months))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))

    return manifest
