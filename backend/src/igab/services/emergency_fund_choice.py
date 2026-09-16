"""Choosing what the emergency fund counts — the picker's read and its one save.

Orchestration only. What the fund IS lives in `services/emergency_fund.py`;
this module writes the three facts it reads, each through the path that
already owns it:

- envelopes: the Emergency fund tag's membership and each row's savings mode
  (`services/tag_membership.set_membership`, the Tags checklist's own save);
- accounts: `counts_toward_emergency_fund`, turning `counts_as_savings` on in
  the same save where the account did not count as savings yet — the flag is
  refused without it (`txn_filters.EMERGENCY_FUND_ACCOUNT_SHAPE`);
- kept elsewhere: the Guide's external binding rows
  (`GuideService.replace_external`).

**One save, one undo.** All of it lands in one `recorder.batch()` inside one
savepoint, so Cmd+Z puts back envelopes, modes, accounts and the declared
amount together, and a refused part writes nothing at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Tag
from igab.domain.exceptions import InvariantViolation
from igab.domain.money import quantize_cents
from igab.repositories.account_repo import AccountRepository
from igab.repositories.category_filters import EMERGENCY_FUND_KEY, SavingsMode
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.txn_filters import EMERGENCY_FUND_ACCOUNT, EMERGENCY_FUND_ACCOUNT_CANDIDATE
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.emergency_fund import CONCEPT_KEY, EmergencyFund, chosen, emergency_fund
from igab.services.tag_membership import set_membership

ZERO = Decimal("0")


@dataclass(frozen=True)
class AccountCandidate:
    """An account the picker offers, and whether the fund counts it now."""

    id: uuid.UUID
    name: str
    balance: Decimal
    counts_as_savings: bool
    #: Counted by the fund today (`EMERGENCY_FUND_ACCOUNT`) — a flag left on an
    #: account that stopped counting as savings reads False, as the fund does.
    member: bool


@dataclass(frozen=True)
class ExternalChoice:
    declared: bool
    amount: Decimal | None
    note: str | None


@dataclass(frozen=True)
class FundChoice:
    add_categories: frozenset[uuid.UUID]
    remove_categories: frozenset[uuid.UUID]
    savings_modes: Mapping[uuid.UUID, SavingsMode | None]
    #: The FULL chosen set of accounts — candidates not in it are unmarked.
    account_ids: frozenset[uuid.UUID]
    external: ExternalChoice


async def emergency_fund_tag(session: AsyncSession, budget_id: uuid.UUID) -> Tag:
    """The budget's Emergency fund tag, seeding the system tags if it lacks it."""
    repo = TagRepository(session)
    tag = await repo.get_system_tag(budget_id, EMERGENCY_FUND_KEY)
    if tag is None:
        await seed_system_tags(session, budget_id)
        tag = await repo.get_system_tag(budget_id, EMERGENCY_FUND_KEY)
    if tag is None:  # pragma: no cover — seeding always creates it
        raise InvariantViolation("This budget has no Emergency fund tag.")
    return tag


async def account_candidates(session: AsyncSession, budget_id: uuid.UUID) -> list[AccountCandidate]:
    rows = (
        await session.execute(
            select(Account, EMERGENCY_FUND_ACCOUNT)
            .where(Account.budget_id == budget_id, EMERGENCY_FUND_ACCOUNT_CANDIDATE)
            .order_by(Account.name, Account.id)
        )
    ).all()
    balances = await AccountRepository(session).balances_for([a.id for a, _ in rows])
    return [
        AccountCandidate(
            id=a.id,
            name=a.name,
            balance=quantize_cents(balances.get(a.id, ZERO)),
            counts_as_savings=a.counts_as_savings,
            member=bool(counted),
        )
        for a, counted in rows
    ]


async def picker(
    session: AsyncSession, budget_id: uuid.UUID
) -> tuple[EmergencyFund, list[AccountCandidate]]:
    return await emergency_fund(session, budget_id), await account_candidates(session, budget_id)


async def save_choice(
    session: AsyncSession,
    recorder: ChangeRecorder,
    budget_id: uuid.UUID,
    choice: FundChoice,
) -> None:
    """Write the picker's save as one change. Raises `InvariantViolation` (and
    writes nothing) for a category outside the taggable set, a mode on a
    category that is not a savings category, or an account that is no
    candidate."""
    from igab.guide.service import GuideService  # the Guide imports the fund's readers

    tag = await emergency_fund_tag(session, budget_id)
    with recorder.batch():
        async with session.begin_nested():
            await set_membership(
                session,
                recorder,
                budget_id,
                tag,
                add=set(choice.add_categories),
                remove=set(choice.remove_categories),
                savings_modes=choice.savings_modes,
            )
            await _set_accounts(session, recorder, budget_id, choice.account_ids)
            categories, accounts = await chosen(session, budget_id)
            await GuideService(session, changes=recorder).replace_external(
                budget_id,
                CONCEPT_KEY,
                declared=choice.external.declared,
                amount=choice.external.amount,
                note=choice.external.note,
                chosen_elsewhere=bool(categories or accounts),
            )


async def _set_accounts(
    session: AsyncSession,
    recorder: ChangeRecorder,
    budget_id: uuid.UUID,
    account_ids: frozenset[uuid.UUID],
) -> None:
    candidates = (
        (
            await session.execute(
                select(Account)
                .where(Account.budget_id == budget_id, EMERGENCY_FUND_ACCOUNT_CANDIDATE)
                .order_by(Account.name, Account.id)
            )
        )
        .scalars()
        .all()
    )
    if account_ids - {a.id for a in candidates}:
        raise InvariantViolation(
            "Only a live, open off-budget account can count toward the emergency fund. "
            "An on-budget account's money is already in its envelopes — tag those instead."
        )
    repo = AccountRepository(session)
    for account in candidates:
        changes: dict[str, bool] = {}
        if account.id in account_ids:
            if not account.counts_as_savings:
                changes["counts_as_savings"] = True
            if not account.counts_toward_emergency_fund:
                changes["counts_toward_emergency_fund"] = True
        elif account.counts_toward_emergency_fund:
            changes["counts_toward_emergency_fund"] = False
        if not changes:
            continue
        before = snapshot("account", account)
        updated = await repo.update(account.id, **changes)
        if updated.counts_toward_emergency_fund:
            await repo.require_emergency_fund_shape(account.id)
        after = snapshot("account", updated)
        if snapshots_match(after, before):
            await recorder.record(
                budget_id=budget_id,
                entity_type="account",
                entity_id=account.id,
                action="update",
                before=before,
                after=after,
            )
