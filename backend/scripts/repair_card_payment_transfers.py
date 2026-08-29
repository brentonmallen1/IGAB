"""Repair budgets damaged before synced transfer legs were paired.

    just repair-transfers                       # dry run, every budget
    just repair-transfers --budget <uuid>        # dry run, one budget
    just repair-transfers --apply                # write
    just repair-transfers --clear-categories     # also link pairs whose
                                                 # categories must go first

Three defects, all produced automatically and all invisible once made:

1. **Unpaired transfer legs.** A bank feed reports each account separately, so
   both sides of one movement arrive with ordinary payees and nothing links
   them. On a card that means the payment never spent the card's reserve; on
   an on-budget savings account it means Ready to Assign gained the whole
   amount out of nowhere. `domain/transfers.pair_legs` decides which pairs are
   unmistakable; this only ever links those.

2. **Card charges filed as income.** An outflow filed to a system (Income)
   category reaches no envelope at all. Card interest lands there on its own,
   because a payee whose history is bank interest categorizes a card's
   interest charge the same way. Uncategorizing it puts the debt in Uncovered,
   where it belongs, and the Accounts page can then suggest a real envelope.

3. **Stranded card payment envelopes.** Left behind when a card account is
   deleted: hidden from the grid, still counted in the envelope term.

Every write goes through `TransactionService` / `CategoryService`, so the whole
repair is change-logged and undoable. Nothing is written without `--apply`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from igab.db.models import Account, Budget, Category, CategoryGroup, Transaction
from igab.domain.matching import DATE_WINDOW_DAYS
from igab.domain.transfers import PairableLeg, pair_legs
from igab.repositories.account_repo import AccountRepository
from igab.repositories.attachment_repo import AttachmentRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.budget_service import BudgetService
from igab.services.card_payment import CARD_PAYMENTS_GROUP
from igab.services.category_service import CategoryService
from igab.services.transaction_service import TransactionService, TransactionUpdate


def _money(value: Decimal) -> str:
    return f"{value:>12,.2f}"


def _category_service(session: AsyncSession) -> CategoryService:
    category_repo = CategoryRepository(session)
    group_repo = CategoryGroupRepository(session)
    assignment_repo = BudgetAssignmentRepository(session)
    transaction_repo = TransactionRepository(session)
    account_repo = AccountRepository(session)
    budget_service = BudgetService(
        account_repo, category_repo, group_repo, assignment_repo, transaction_repo
    )
    return CategoryService(
        session, category_repo, group_repo, budget_service, transaction_repo, assignment_repo
    )


def _services(session: AsyncSession) -> TransactionService:
    return TransactionService(
        session,
        TransactionRepository(session),
        AccountRepository(session),
        CategoryRepository(session),
        PayeeRepository(session),
        attachment_repo=AttachmentRepository(session),
    )


async def _unpaired_legs(
    session: AsyncSession, budget_id: uuid.UUID, apply: bool, clear_categories: bool
) -> int:
    """Link every pair `pair_legs` is certain about.

    Linking two on-budget legs must clear both categories — an internal
    movement is not spending. Unlike a sync, a repair cannot tell a person's
    category from an old auto-categorized guess: the rows are months old and
    nothing recorded which was which. So the default is to refuse, listing what
    would be cleared, and `--clear-categories` is the operator saying they have
    read the list and agree.

    That is exactly the decision this repair exists for. The card payments that
    started all of this are categorized on both sides — checking to a hand-made
    "Citi Card" envelope, the card leg to whatever auto-categorization guessed
    — and neither category may survive the link.
    """
    accounts = {
        a.id: a
        for a in (
            await session.execute(
                select(Account).where(
                    Account.budget_id == budget_id,
                    Account.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars()
    }
    rows = (
        (
            await session.execute(
                select(Transaction)
                .where(
                    Transaction.budget_id == budget_id,
                    Transaction.is_deleted == False,  # noqa: E712
                    Transaction.parent_transaction_id.is_(None),
                    Transaction.is_split == False,  # noqa: E712
                    Transaction.transfer_id.is_(None),
                )
                .order_by(Transaction.date)
            )
        )
        .scalars()
        .all()
    )
    legs = [
        PairableLeg(
            id=r.id,
            account_id=r.account_id,
            on_budget=accounts[r.account_id].on_budget,
            date=r.date,
            amount=r.amount,
            categorized=r.category_id is not None,
            category_is_a_guess=clear_categories,
        )
        for r in rows
        if r.account_id in accounts
    ]
    confident, review = pair_legs(legs, window_days=DATE_WINDOW_DAYS)
    by_id = {r.id: r for r in rows}
    service = _services(session)

    categories = {
        c.id: c.name
        for c in (
            await session.execute(select(Category).where(Category.budget_id == budget_id))
        ).scalars()
    }
    for pair in confident:
        out, inn = by_id[pair.outflow_id], by_id[pair.inflow_id]
        print(
            f"    link {_money(out.amount)}  {accounts[out.account_id].name}"
            f" -> {accounts[inn.account_id].name}  ({out.date})"
        )
        for cid in pair.clears_categories:
            row = by_id[cid]
            name = categories.get(row.category_id, "?")
            print(f"         clears category '{name}' from the {accounts[row.account_id].name} leg")
        if apply:
            await service.link_legs(budget_id, out, inn, clear_categories=pair.clears_categories)

    blocked_by_categories = [p for p in review if p.clears_categories]
    if blocked_by_categories and not clear_categories:
        print(
            f"    {len(blocked_by_categories)} pair(s) need a category cleared to link. "
            "Re-run with --clear-categories to see and make those changes:"
        )
        for pair in blocked_by_categories:
            out, inn = by_id[pair.outflow_id], by_id[pair.inflow_id]
            print(
                f"      would link {_money(out.amount)}  {accounts[out.account_id].name}"
                f" -> {accounts[inn.account_id].name}  ({out.date})"
            )
    ambiguous = len(review) - len(blocked_by_categories)
    if ambiguous:
        print(
            f"    ({ambiguous} pair(s) left alone as ambiguous — more than one row could be "
            "the other side. Accounts \u2192 hygiene lists them.)"
        )
    return len(confident)


async def _card_rows_filed_as_income(
    session: AsyncSession, budget_id: uuid.UUID, apply: bool
) -> int:
    rows = (
        await session.execute(
            select(Transaction, Category.name)
            .join(Category, Category.id == Transaction.category_id)
            .join(CategoryGroup, CategoryGroup.id == Category.category_group_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.is_deleted == False,  # noqa: E712
                Transaction.amount < 0,
                CategoryGroup.is_system == True,  # noqa: E712
                Account.is_deleted == False,  # noqa: E712
                Account.on_budget == True,  # noqa: E712
                Account.classification == "liability",
            )
            .order_by(Transaction.date)
        )
    ).all()
    service = _services(session)
    for txn, category_name in rows:
        print(f"    unfile {_money(txn.amount)}  {txn.date}  from income '{category_name}'")
        if apply:
            await service.update(budget_id, txn.id, TransactionUpdate(category_id=None))
    return len(rows)


async def _stranded_card_envelopes(session: AsyncSession, budget_id: uuid.UUID, apply: bool) -> int:
    live_cards = {
        a
        for a in (
            await session.execute(
                select(Account.id).where(
                    Account.budget_id == budget_id,
                    Account.is_deleted == False,  # noqa: E712
                    Account.on_budget == True,  # noqa: E712
                    Account.classification == "liability",
                )
            )
        ).scalars()
    }
    envelopes = (
        (
            await session.execute(
                select(Category)
                .join(CategoryGroup, CategoryGroup.id == Category.category_group_id)
                .where(
                    Category.budget_id == budget_id,
                    Category.is_deleted == False,  # noqa: E712
                    CategoryGroup.name == CARD_PAYMENTS_GROUP,
                )
            )
        )
        .scalars()
        .all()
    )
    stranded = [c for c in envelopes if c.linked_account_id not in live_cards]
    if not stranded:
        return 0
    # The real delete path, not a raw is_deleted flip: it decides what becomes
    # of anything pointing at the category, records the change, and is
    # undoable. `move_to=None` leaves any rows genuinely uncategorized, which
    # is correct here — nothing may be filed to a card envelope in the first
    # place (`require_not_card_envelope`).
    service = _category_service(session)
    for category in stranded:
        print(f"    drop stranded card envelope '{category.name}' ({category.id})")
    if apply:
        await service.delete_categories(budget_id, [c.id for c in stranded], move_to=None)
    return len(stranded)


async def _report_unfinished_migration(session: AsyncSession, budget_id: uuid.UUID) -> None:
    """Say what is left to do after payments become transfers.

    Turning a payment into a transfer draws on the card's reserve. Someone who
    budgeted card payments the pre-card-account way — a hand-made "Citi Card"
    envelope, funded monthly, spent by categorizing the payment — has all that
    money in the wrong envelope, so the card's reserve goes negative by the
    whole amount while the old envelope keeps a matching surplus.

    Ready to Assign is right either way: the two cancel exactly. But a reserve
    of -10,749.82 beside an envelope holding +10,857.08 is not a state to hand
    someone without a sentence explaining it, and squaring it is one budget
    move that only the operator can decide to make.
    """
    service = BudgetService(
        AccountRepository(session),
        CategoryRepository(session),
        CategoryGroupRepository(session),
        BudgetAssignmentRepository(session),
        TransactionRepository(session),
    )
    summary = await service.get_budget_summary(budget_id, date.today().replace(day=1))
    names = {
        c.id: c.name
        for c in await CategoryRepository(session).get_all(budget_id, include_hidden=True)
    }
    for card in summary.cards:
        if card.set_aside >= 0:
            continue
        need = -card.set_aside
        print(f"\n    NEXT STEP — '{card.name}' now has a reserve of {_money(card.set_aside)}.")
        print(
            "      Its payments are transfers now, so they draw on the card's reserve\n"
            "      rather than on a spending envelope. The money that funded them is\n"
            "      still in whichever envelope you were using before."
        )
        surplus = [
            b
            for b in summary.category_balances
            if not b.is_card_payment and not b.in_system_group and b.available >= need
        ]
        for b in sorted(surplus, key=lambda b: abs(b.available - need))[:2]:
            print(
                f"      '{names.get(b.category_id, '?')}' holds {_money(b.available)} — "
                f"moving {_money(need)} of it to '{card.name}' squares both."
            )
        if not surplus:
            print(f"      Assign {_money(need)} to '{card.name}' to square it.")


async def run(database_url: str, budget_id: uuid.UUID | None, apply: bool, args_clear: bool) -> int:
    engine = create_async_engine(database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    total = 0
    async with Session() as session:
        q = select(Budget)
        if budget_id is not None:
            q = q.where(Budget.id == budget_id)
        budgets = (await session.execute(q)).scalars().all()
        for budget in budgets:
            print(f"\n  budget {budget.name} ({budget.id})")
            linked = await _unpaired_legs(session, budget.id, apply, args_clear)
            unfiled = await _card_rows_filed_as_income(session, budget.id, apply)
            dropped = await _stranded_card_envelopes(session, budget.id, apply)
            found = linked + unfiled + dropped
            total += found
            if not found:
                print("    nothing to repair")
            if linked:
                await _report_unfinished_migration(session, budget.id)
        if apply:
            await session.commit()
        else:
            await session.rollback()
    await engine.dispose()
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=uuid.UUID, default=None, help="one budget id")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument(
        "--clear-categories",
        action="store_true",
        help="permit clearing a category where linking a pair requires it",
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args(argv)

    if not args.database_url:
        print("set DATABASE_URL or pass --database-url", file=sys.stderr)
        return 2

    print("DRY RUN — nothing will be written." if not args.apply else "APPLYING.")
    total = asyncio.run(run(args.database_url, args.budget, args.apply, args.clear_categories))
    verb = "repaired" if args.apply else "would repair"
    print(f"\n{verb} {total} item(s).")
    if not args.apply and total:
        print("Re-run with --apply to write. Take a backup first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
