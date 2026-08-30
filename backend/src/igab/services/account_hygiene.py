"""Post-import account hygiene: things that are probably wrong, not provably.

Deliberately **not** part of `IntegrityService`. That service reports invariant
violations — splits that do not sum, money that is not conserved — and a clean
run there has to keep meaning "the arithmetic is sound". A dormant account or a
suspicious account type is a suggestion, and mixing the two would make a clean
integrity run stop meaning anything.

Everything here is a judgement call the user can dismiss, and every finding
leads somewhere it can be acted on. A finding with no next step is criticism.

Why this exists at all: a real 47-account YNAB import produced a budget the
user described as "a complete mess". The importer was correct — 47 names in,
47 accounts out — but four assets had been given debt types in the mapping
form, understating net worth by ~$2.8M and spawning four phantom companion
liabilities, and 1,117 transfer legs arrived unpaired. Nothing said so. The
mapping step now makes those choices harder to make quietly; this catches what
still gets through, and repairs budgets imported before any of it existed.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.api.v1.imports import _TRACKED_HINTS, _matches, _normalize_for_match
from igab.db.models import Account, Liability, Transaction
from igab.guide.detection import budget_service_from
from igab.repositories.category_filters import IN_SYSTEM_GROUP
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.txn_filters import (
    CARD_ACCOUNT,
    LEAF,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    POSTED,
    UNPAIRED_TRANSFER_LEG,
    row_category,
)
from igab.utils.clock import today_utc

#: Months without a posted transaction before an open account reads as dormant.
#: Matches the import step's threshold so the two never disagree about the same
#: account.
DORMANT_AFTER_MONTHS = 12

#: How far a balance must sit on the wrong side of its classification before we
#: say so. Not zero: a credit card paid in full often rests slightly positive,
#: and a finding on every paid-off card is one people learn to scroll past.
SIGN_MISMATCH_FLOOR = 1000


@dataclass
class HygieneFinding:
    #: Stable key, so the frontend can route the fix without parsing prose.
    kind: str
    title: str
    detail: str
    #: What to do about it, in the user's terms.
    action: str
    #: Accounts this is about, most-relevant first.
    account_ids: list[uuid.UUID] = field(default_factory=list)
    #: For findings that lead to transactions rather than to an account.
    transaction_count: int = 0


@dataclass
class HygieneReport:
    findings: list[HygieneFinding]

    @property
    def clean(self) -> bool:
        return not self.findings


class AccountHygieneService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self, budget_id: uuid.UUID) -> HygieneReport:
        accounts = await self._accounts(budget_id)
        findings = [
            # Order is the ranking. On-budget-but-tracked leads because it is
            # the only one here that corrupts a number the user reads daily:
            # to_be_assigned is total account balance minus category balances,
            # so a house inside the budget poisons every envelope figure.
            await self._tracked_name_on_budget(accounts),
            await self._liability_with_positive_balance(accounts),
            await self._unpaired_transfer_legs(budget_id),
            await self._categorized_tracking_rows(budget_id),
            await self._card_rows_filed_as_income(budget_id),
            await self._dormant_open_accounts(accounts, budget_id),
            await self._stale_companion_liabilities(budget_id, accounts),
            await self._money_in_an_archived_envelope(budget_id),
        ]
        return HygieneReport(findings=[f for f in findings if f is not None])

    async def _accounts(self, budget_id: uuid.UUID) -> list[Account]:
        rows = await self.session.execute(
            select(Account)
            .where(Account.budget_id == budget_id, Account.is_deleted == False)  # noqa: E712
            .order_by(Account.name)
        )
        return list(rows.scalars().all())

    async def _balances(self, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
        """Posted parent-row sums, matching AccountRepository.get_balance."""
        if not account_ids:
            return {}
        rows = await self.session.execute(
            select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.account_id.in_(account_ids),
                NOT_DELETED,
                POSTED,
                Transaction.parent_transaction_id.is_(None),
            )
            .group_by(Transaction.account_id)
        )
        return {aid: float(total) for aid, total in rows.all()}

    async def _tracked_name_on_budget(self, accounts: list[Account]) -> HygieneFinding | None:
        hits = [
            a
            for a in accounts
            if a.on_budget and _matches(_normalize_for_match(a.name), _TRACKED_HINTS)
        ]
        if not hits:
            return None
        return HygieneFinding(
            kind="tracked_name_on_budget",
            title=f"{len(hits)} account{'s' if len(hits) > 1 else ''} may belong off budget",
            detail=(
                "The name reads like something you own outright — a house, a vehicle, a "
                "piece of land — but the account is on budget. An on-budget balance funds "
                "Ready to Assign, so a tracked thing sitting inside the budget inflates "
                "every envelope figure you have."
            ),
            action="Open the account's settings and turn off 'on budget'.",
            account_ids=[a.id for a in hits],
        )

    async def _liability_with_positive_balance(
        self, accounts: list[Account]
    ) -> HygieneFinding | None:
        debts = [a for a in accounts if a.classification == "liability"]
        balances = await self._balances([a.id for a in debts])
        hits = [a for a in debts if balances.get(a.id, 0.0) > SIGN_MISMATCH_FLOOR]
        if not hits:
            return None
        return HygieneFinding(
            kind="liability_positive_balance",
            title=f"{len(hits)} debt account{'s' if len(hits) > 1 else ''} hold a positive balance",
            detail=(
                "A debt-typed account is subtracted from net worth. Holding a positive "
                "balance usually means it is really something you own that was given a "
                "debt type by mistake — which moves net worth by twice the balance. An "
                "overpaid loan is real, though, so this is worth a look rather than a fix."
            ),
            action="Check the balance, and change the account type if it is an asset.",
            account_ids=[a.id for a in hits],
        )

    async def _unpaired_transfer_legs(self, budget_id: uuid.UUID) -> HygieneFinding | None:
        count = (
            await self.session.execute(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.budget_id == budget_id, NOT_DELETED, UNPAIRED_TRANSFER_LEG)
            )
        ).scalar_one()
        if not count:
            return None
        return HygieneFinding(
            kind="unpaired_transfer_legs",
            title=f"{count:,} transfer{'s' if count != 1 else ''} never found their other side",
            detail=(
                "The payee names another account, but no transaction links back. Balances "
                "are right either way, since both sides were written — but nothing marks "
                "these as money moving between your own accounts, so reports can read them "
                "as real income or spending. This is usually what an account left out of an "
                "import leaves behind."
            ),
            action=(
                "Match them up links every leg whose other side is unmistakable, "
                "without touching a single amount. Whatever is left is ambiguous or "
                "genuinely one-sided — open one to pick its partner or add the missing row."
            ),
            transaction_count=int(count),
        )

    async def _card_rows_filed_as_income(self, budget_id: uuid.UUID) -> HygieneFinding | None:
        """Money going OUT on a credit card, filed to an income category.

        A charge on a card is not income under any reading, and filing it there
        makes it reach nothing: the envelope term skips system groups, and the
        card's reservation arithmetic only walks spending categories
        (`category_filters.SPENDABLE`, which is why the *inflow* side of the
        same misfiling had to be named rather than dropped —
        `txn_filters.UNBUDGETED_CARD_CREDIT`). The
        balance moves and the budget never mentions it — the charge ends up in
        Uncovered with no envelope ever naming it.

        Not an integrity failure, which is why it lives here: the arithmetic is
        the same as leaving the row uncategorized, so no money is lost. It is a
        *visibility* defect, and it is worth surfacing because the way rows get
        here is automatic. Three months of card interest landed on "Ready to
        Assign" because the payee carried a mapping sample of "Interest" and
        the bank called the row "Interest Charge".

        Cash accounts are deliberately excluded. There, an outflow filed to an
        income category is arithmetically identical to an uncategorized one and
        is YNAB's own convention for a reconciliation adjustment — flagging
        those would bury this signal under decades of correct rows.
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                NOT_DELETED,
                Transaction.amount < 0,
                row_category(IN_SYSTEM_GROUP),
                CARD_ACCOUNT,
            )
        )
        count = result.scalar_one()
        if not count:
            return None
        return HygieneFinding(
            kind="card_rows_filed_as_income",
            title=f"{count:,} card charge{'s' if count != 1 else ''} filed as income",
            detail=(
                "A charge on a credit card is not income, and filing it to an income "
                "category means no envelope ever sees it — the card's balance moves, the "
                "debt lands in Uncovered, and nothing in the budget names the spending. "
                "Interest charges reach this state on their own, because a payee whose "
                "history is bank interest will happily categorize a card's interest "
                "charge the same way."
            ),
            action=(
                "Give them a real envelope — an Interest or Bank Fees category — so the "
                "money is budgeted and shows up in reports. Leaving them uncategorized is "
                "also honest; it keeps them in Uncovered without claiming they were income."
            ),
            transaction_count=int(count),
        )

    async def _money_in_an_archived_envelope(self, budget_id: uuid.UUID) -> HygieneFinding | None:
        """Money sitting in an envelope the budget no longer draws.

        Archiving refuses to leave a balance behind — `CategoryService.
        archive_categories` blocks on it and the dialog says which envelope to
        empty first. This finds the ones that predate that rule: the old
        behaviour flipped a flag, kept the money, and said nothing, and the
        route back was a "Show hidden" toggle that no longer exists.

        The amount still counts toward Ready to Assign, so nothing is lost —
        it is simply somewhere the user cannot see or spend it. That is a
        visibility defect rather than an arithmetic one, which is why it lives
        here rather than in the integrity check.

        Read from `get_budget_summary` rather than re-derived: its
        `category_balances` include archived categories precisely so this can
        see them, and a second carryover simulation here would be a copy of the
        one rule this app most needs to have only once.
        """
        summary = await budget_service_from(self.session).get_budget_summary(budget_id, today_utc())
        archived = {
            c.id: c
            for c in await CategoryRepository(self.session).get_all(
                budget_id, include_archived=True
            )
            if c.is_archived
        }
        stranded = [
            b for b in summary.category_balances if b.category_id in archived and b.available != 0
        ]
        if not stranded:
            return None
        total = sum((b.available for b in stranded), Decimal("0"))
        names = ", ".join(sorted(archived[b.category_id].name for b in stranded)[:3])
        more = "" if len(stranded) <= 3 else f" and {len(stranded) - 3} more"
        return HygieneFinding(
            kind="money_in_an_archived_envelope",
            title=(
                f"{len(stranded)} archived envelope{'s' if len(stranded) != 1 else ''} "
                "still holds money"
            ),
            detail=(
                f"{names}{more} — {total} in total. Archived envelopes are not drawn on the "
                "budget, so this money is counted but not visible, and nothing on the budget "
                "page can move it. Archiving refuses to leave a balance behind now; these "
                "predate that."
            ),
            action=(
                "Open See archived on the budget, restore each one, and move its balance "
                "somewhere you can see it. You can archive it again straight afterwards."
            ),
        )

    async def _categorized_tracking_rows(self, budget_id: uuid.UUID) -> HygieneFinding | None:
        """Rows on off-budget accounts that carry a category.

        The rule they break lives in domain/transfers.py: a category may sit
        only on an on-budget row. These predate the rule being enforced — an
        import, a sync's payee-memory categorization, an account flipped off
        budget after the fact. The budget's activity sums exclude them, so
        they move no money; they are still spending the register claims and
        the budget never counted, which is a lie waiting for a reader.
        """
        count = (
            await self.session.execute(
                select(func.count())
                .select_from(Transaction)
                .where(
                    Transaction.budget_id == budget_id,
                    NOT_DELETED,
                    LEAF,
                    Transaction.category_id.isnot(None),
                    ~ON_BUDGET_ACCOUNT,
                )
            )
        ).scalar_one()
        if not count:
            return None
        return HygieneFinding(
            kind="categorized_tracking_rows",
            title=(
                f"{count:,} transaction{'s' if count != 1 else ''} on tracking accounts "
                "carry a category"
            ),
            detail=(
                "Off-budget activity is net-worth movement, not budget spending, so these "
                "categories count nowhere — the budget and every report leave them out. "
                "They usually arrive with an import, a sync that learned the category from "
                "the payee, or an account moved off budget after the fact."
            ),
            action=(
                "Remove the categories strips every one in a single undoable step. "
                "Amounts, dates and accounts are untouched."
            ),
            transaction_count=int(count),
        )

    async def _dormant_open_accounts(
        self, accounts: list[Account], budget_id: uuid.UUID
    ) -> HygieneFinding | None:
        open_ids = [a.id for a in accounts if not a.is_closed]
        if not open_ids:
            return None
        cutoff = date.today() - timedelta(days=DORMANT_AFTER_MONTHS * 30)
        rows = await self.session.execute(
            select(Transaction.account_id, func.max(Transaction.date))
            .where(Transaction.account_id.in_(open_ids), NOT_DELETED, POSTED)
            .group_by(Transaction.account_id)
        )
        last_seen: dict[uuid.UUID, date] = {aid: seen for aid, seen in rows.all()}
        # An account with no transactions at all is not dormant — it is new,
        # and nagging about an account someone just opened is the opposite of
        # helpful.
        hits = [a for a in accounts if last_seen.get(a.id) and last_seen[a.id] < cutoff]
        if not hits:
            return None
        return HygieneFinding(
            kind="dormant_open_account",
            title=f"{len(hits)} open account{'s have' if len(hits) > 1 else ' has'} gone quiet",
            detail=(
                f"Nothing posted in over {DORMANT_AFTER_MONTHS} months. Closing an account "
                "keeps every transaction — net worth over time, reports and history are "
                "untouched — and only takes it out of the account pickers and report "
                "filters. You can reopen it whenever."
            ),
            action="Close the ones you have finished with.",
            account_ids=[a.id for a in hits],
        )

    async def _stale_companion_liabilities(
        self, budget_id: uuid.UUID, accounts: list[Account]
    ) -> HygieneFinding | None:
        """A companion liability whose account is no longer a debt.

        Retyping an account away from a debt type leaves its companion behind
        at $0 — recorded as a known gap when companion liabilities landed. It
        is the residue of exactly the mistake this whole panel is about: four
        assets given debt types produced four phantom debts, and correcting the
        type does not remove them.
        """
        non_debt_ids = [a.id for a in accounts if a.classification != "liability"]
        if not non_debt_ids:
            return None
        rows = await self.session.execute(
            select(Liability).where(
                Liability.budget_id == budget_id,
                Liability.linked_account_id.in_(non_debt_ids),
                Liability.is_deleted == False,  # noqa: E712
            )
        )
        stale = list(rows.scalars().all())
        if not stale:
            return None
        return HygieneFinding(
            kind="stale_companion_liability",
            title=f"{len(stale)} payoff record{'s' if len(stale) > 1 else ''} outlived its account",
            detail=(
                "These track the payoff of an account that is no longer a debt — usually "
                "because the type was corrected after the import. They are counted nowhere, "
                "but they clutter the Liabilities page and read as debts you do not have."
            ),
            action="Delete them from the Liabilities page.",
            account_ids=[
                liability.linked_account_id for liability in stale if liability.linked_account_id
            ],
        )
