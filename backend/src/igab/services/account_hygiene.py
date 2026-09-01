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
from igab.domain.card_timeline import card_timeline, first_breach
from igab.domain.cards import card_reserve
from igab.domain.matching import DATE_WINDOW_DAYS
from igab.domain.transfers import PairableLeg, pair_legs
from igab.guide.detection import budget_service_from
from igab.repositories.category_filters import IN_SYSTEM_GROUP
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.txn_filters import (
    CARD_ACCOUNT,
    LEAF,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    PAIRABLE_LEG,
    POSTED,
    UNPAIRED_TRANSFER_LEG,
    row_category,
)
from igab.utils.clock import today_utc

#: Months without a posted transaction before an open account reads as dormant.
#: Matches the import step's threshold so the two never disagree about the same
#: account.
DORMANT_AFTER_MONTHS = 12

#: How far back to look for two rows that are one card payment. The pairing
#: pass only ever runs over rows a sync just created, so a budget that already
#: holds both legs — a card added later and back-filled, an import — never gets
#: one. Bounded because `pair_legs` compares every outflow against every inflow
#: in the window.
UNLINKED_PAYMENT_LOOKBACK_DAYS = 180

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
        # One summary and one card walk, shared by every detector that reads
        # them — the walk is the app's most expensive computation, and each
        # detector re-running it is a page that gets slower per finding.
        budget_service = budget_service_from(self.session)
        today = today_utc()
        summary = await budget_service.get_budget_summary(budget_id, today)
        walk = await budget_service.card_walk(budget_id, today.replace(day=1))
        findings = [
            # Order is the ranking. On-budget-but-tracked leads because it is
            # the only one here that corrupts a number the user reads daily:
            # to_be_assigned is total account balance minus category balances,
            # so a house inside the budget poisons every envelope figure.
            await self._tracked_name_on_budget(accounts),
            await self._liability_with_positive_balance(accounts),
            await self._unpaired_transfer_legs(budget_id),
            await self._unlinked_card_payments(budget_id),
            self._card_reserve_went_negative(summary, walk),
            await self._card_debt_predates_budget(budget_id, summary, walk),
            *(await self._misfiled_card_inflows(budget_id, walk)),
            await self._payment_envelope_shadow(budget_id, summary),
            await self._categorized_tracking_rows(budget_id),
            await self._card_rows_filed_as_income(budget_id),
            await self._dormant_open_accounts(accounts, budget_id),
            await self._stale_companion_liabilities(budget_id, accounts),
            await self._money_in_an_archived_envelope_from(budget_id, summary),
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

    async def _unlinked_card_payments(self, budget_id: uuid.UUID) -> HygieneFinding | None:
        """A card credit and a cash debit that are one payment, still unlinked.

        Distinct from `_unpaired_transfer_legs`, which finds rows whose PAYEE
        already names another account. Two synced legs of one card payment
        arrive with ordinary bank payees on both sides, so that finding never
        sees them — and `repair_transfers` is payee-based too, so neither does
        the repair. The amount-based pass (`pair_legs`) only ever runs over
        rows a sync just created, which means a budget that already holds both
        legs has no path to the answer at all.

        That gap is what a real card looked like: `paid to the card` reading
        zero while thousands of debt was repaid, the payment sitting in the
        "other credits" term, and the reserve untouched because only a
        transfer spends it.

        The decision is `domain/transfers.pair_legs` — the same pure function
        the sync uses, not a second opinion about what makes two rows one
        movement. Pairs it calls confident are reported as safe; pairs it
        holds for review are counted separately, because those need a person
        (usually to clear a category off the cash leg, which linking must do
        and which is never done unattended).
        """
        cutoff = today_utc() - timedelta(days=UNLINKED_PAYMENT_LOOKBACK_DAYS)
        rows = list(
            (
                await self.session.execute(
                    select(Transaction)
                    .join(Account, Account.id == Transaction.account_id)
                    .where(
                        Account.budget_id == budget_id,
                        PAIRABLE_LEG,
                        Transaction.date >= cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return None

        accounts = {a.id: a for a in await self._accounts(budget_id)}
        legs = [
            PairableLeg(
                id=r.id,
                account_id=r.account_id,
                on_budget=accounts[r.account_id].on_budget,
                date=r.date,
                amount=r.amount,
                categorized=r.category_id is not None,
                # Nothing here is this run's own guess: a sync's guesses are
                # only clearable by the sync that made them, moments later.
                category_is_a_guess=False,
            )
            for r in rows
            if r.account_id in accounts
        ]
        confident, review = pair_legs(legs, window_days=DATE_WINDOW_DAYS)

        cards = {a.id for a in accounts.values() if a.classification == "liability"}
        by_id = {r.id: r for r in rows}
        involved = [
            pair
            for pair in (*confident, *review)
            if by_id[pair.inflow_id].account_id in cards
            or by_id[pair.outflow_id].account_id in cards
        ]
        if not involved:
            return None

        card_ids = list(
            dict.fromkeys(
                acct
                for pair in involved
                for acct in (by_id[pair.inflow_id].account_id, by_id[pair.outflow_id].account_id)
                if acct in cards
            )
        )
        total = sum((abs(by_id[p.inflow_id].amount) for p in involved), Decimal("0"))
        n = len(involved)
        return HygieneFinding(
            kind="unlinked_card_payments",
            title=f"{n:,} card payment{'s' if n != 1 else ''} may never have been linked",
            detail=(
                f"A credit on a card and a debit from one of your own accounts, same "
                f"amount and within a few days, with nothing joining them — "
                f"{total:,.2f} in total. Only a transfer spends a card's set-aside, so "
                f"until these are linked the card reads 'paid 0.00' while its balance "
                f"visibly falls, and the money shows up as a credit that came from "
                f"nowhere. Balances are right either way; what is wrong is the story."
            ),
            action=(
                "Open one and pick its partner. Where the payment on the cash side "
                "sits in a spending envelope, linking has to clear that category — "
                "an internal transfer is not spending — so that choice is yours to "
                "make rather than something a sync does quietly."
            ),
            account_ids=card_ids,
            transaction_count=n,
        )

    async def _card_rows_filed_as_income(self, budget_id: uuid.UUID) -> HygieneFinding | None:
        """Money going OUT on a credit card, filed to an income category.

        A charge on a card is not income under any reading, and filing it there
        makes it reach nothing: the envelope term skips system groups, and the
        card's reservation arithmetic only walks spending categories
        (`category_filters.SPENDABLE`, which is why the *inflow* side of the
        same misfiling had to be named rather than dropped —
        `txn_filters.UNCLAIMED_CARD_ROW`). The
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

    #: How the timeline's leg names read in a sentence. One spelling — the
    #: breach ranks by `card_timeline.LEG_SIGNS` names, and prose written at
    #: each call site is how the same leg gets three descriptions.
    _LEG_PHRASES = {
        "payments": "a payment ran past everything reserved",
        "residual": "money came back onto the card beyond anything an envelope charged to it",
        "assignments": "more money was moved back out of the card's envelope than it held",
        "released": "a refund released reserved cash",
        "reservations": "funded spending reserved",
    }

    def _card_reserve_went_negative(self, summary, walk) -> HygieneFinding | None:
        """A card's Ready to pay below zero while the card is not in credit.

        A legitimate position, not an integrity failure — the reserve is
        deliberately unfloored (domain/cards.py `CardReserve`) — but on a
        card that still owes money it always has a cause worth reading, and
        the row itself only shows the current figure. This names WHEN it
        crossed and which leg did it, out of the same walk the row is served
        from (`domain/card_timeline.py`).
        """
        lines: list[str] = []
        account_ids: list[uuid.UUID] = []
        for card in summary.cards:
            if card.set_aside >= 0 or card.card_credit > 0:
                continue
            reserve = card_reserve(
                walk.funding, card.account_id, walk.payments.get(card.account_id, {})
            )
            breach = first_breach(
                card_timeline(reserve, {}, walk.funding.riding_by_card.get(card.account_id, {}))
            )
            account_ids.append(card.account_id)
            if breach is None:
                lines.append(f"{card.name} is at {card.set_aside}.")
                continue
            leg, _amount = breach.ranked_legs[0]
            phrase = self._LEG_PHRASES.get(leg, leg)
            lines.append(
                f"{card.name} first crossed below zero in "
                f"{breach.month.strftime('%B %Y')}, when {phrase}."
            )
        if not lines:
            return None
        count = len(lines)
        return HygieneFinding(
            kind="card_reserve_went_negative",
            title=(f"{count} card{'s' if count != 1 else ''} with Ready to pay below zero"),
            detail=" ".join(lines),
            action=(
                "Read the card's Ready to pay breakdown on the budget page for the "
                "month it names. A reimbursement or misfiled refund is fixed by "
                "re-filing the inflow; a payment that ran ahead of the budget is "
                "settled by assigning that much to the card."
            ),
            account_ids=account_ids,
        )

    async def _card_debt_predates_budget(
        self, budget_id: uuid.UUID, summary, walk
    ) -> HygieneFinding | None:
        """A card that was charged before anything ever reserved against it.

        The synced-history shape: a card arrives carrying months of bank
        history from before the budget used it, nothing reserves against that
        debt, and every full-statement payment then drives the reserve down
        by money the budget never set aside. Only cards still showing
        uncovered debt are named — a fully covered card has nothing left to
        act on — and only cards where reserving DID later begin: a card with
        no reserving at all is simply unfiled spending, which its own row
        already explains (`cardRow.emptyLegsNote`), and flagging every fresh
        card would bury the signal.
        """
        first_reserving: dict[uuid.UUID, date] = {}
        for series_by_card in (
            walk.funding.reservations_by_card,
            walk.funding.assignments_by_card,
        ):
            for card_id, series in series_by_card.items():
                months = [m for m, v in series.items() if v > 0]
                if not months:
                    continue
                first = min(months)
                if card_id not in first_reserving or first < first_reserving[card_id]:
                    first_reserving[card_id] = first

        card_ids = [c.account_id for c in summary.cards if c.uncovered > 0]
        if not card_ids:
            return None
        rows = await self.session.execute(
            select(Transaction.account_id, func.min(Transaction.date))
            .where(
                Transaction.account_id.in_(card_ids),
                NOT_DELETED,
                POSTED,
                Transaction.parent_transaction_id.is_(None),
                Transaction.amount < 0,
            )
            .group_by(Transaction.account_id)
        )
        first_charge = {aid: d.replace(day=1) for aid, d in rows.all()}

        lines: list[str] = []
        account_ids: list[uuid.UUID] = []
        for card in summary.cards:
            if card.uncovered <= 0:
                continue
            charged = first_charge.get(card.account_id)
            reserved = first_reserving.get(card.account_id)
            if charged is None or reserved is None or charged >= reserved:
                continue
            account_ids.append(card.account_id)
            lines.append(
                f"{card.name} has charges since {charged.strftime('%B %Y')} and "
                f"nothing reserved until {reserved.strftime('%B %Y')}."
            )
        if not lines:
            return None
        count = len(lines)
        return HygieneFinding(
            kind="card_debt_predates_budget",
            title=(f"{count} card{'s' if count != 1 else ''} carrying debt older than the budget"),
            detail=(
                " ".join(lines)
                + " Spending from before the budget reserves nothing, so it reads as "
                "Uncovered — and a payment covering it spends reserve the budget "
                "never set aside."
            ),
            action=(
                "Assign to the card to cover the old debt, or set the account's "
                "budget start date so its early history reads as opening position."
            ),
            account_ids=account_ids,
        )

    async def _misfiled_card_inflows(
        self, budget_id: uuid.UUID, walk
    ) -> list[HygieneFinding | None]:
        """Card inflows filed to an envelope that never charged that card.

        Exposure is per (category, card) — deliberately, see domain/cards.py —
        so such an inflow releases nothing and reduces the card's reserve
        outright (`residual_by_pair`). Two findings, because the remedies
        differ: an envelope that charged a DIFFERENT card points at a payment
        or refund filed onto the wrong card; one that charged no card at all
        points at a reimbursement or a misfiled deposit.
        """
        names = {a.id: a.name for a in walk.card_accounts}
        categories = {
            c.id: c.name
            for c in await CategoryRepository(self.session).get_all(
                budget_id, include_archived=True
            )
        }

        def charged(cat_id: uuid.UUID, card_id: uuid.UUID) -> bool:
            series = walk.credit_outflows.get(cat_id, {}).get(card_id, {})
            return any(v > 0 for v in series.values())

        other_card: list[str] = []
        other_ids: list[uuid.UUID] = []
        uncharged: list[str] = []
        uncharged_ids: list[uuid.UUID] = []
        for (cat_id, card_id), series in walk.funding.residual_by_pair.items():
            total = sum(series.values(), Decimal("0"))
            if total <= 0 or charged(cat_id, card_id):
                continue
            cat_name = categories.get(cat_id, "an envelope")
            card_name = names.get(card_id, "a card")
            elsewhere = [
                names.get(k, "another card")
                for k in walk.credit_outflows.get(cat_id, {})
                if k != card_id and charged(cat_id, k)
            ]
            if elsewhere:
                other_card.append(
                    f"{total} onto {card_name} via {cat_name}, whose card spending is on "
                    f"{', '.join(sorted(set(elsewhere)))}."
                )
                other_ids.append(card_id)
            else:
                uncharged.append(f"{total} onto {card_name} via {cat_name}.")
                uncharged_ids.append(card_id)

        findings: list[HygieneFinding | None] = []
        if other_card:
            findings.append(
                HygieneFinding(
                    kind="card_inflow_belongs_to_other_card",
                    title="Card inflows whose envelope charged a different card",
                    detail=(
                        " ".join(other_card)
                        + " Exposure is per card, so these released nothing — each one "
                        "reduced its card's Ready to pay outright."
                    ),
                    action=(
                        "If the inflow was a payment or refund for the other card, move "
                        "the transaction to that card's register. If it genuinely landed "
                        "here, assign the same amount to this card to square the reserve."
                    ),
                    account_ids=sorted(set(other_ids), key=str),
                )
            )
        if uncharged:
            findings.append(
                HygieneFinding(
                    kind="residual_on_uncharged_category",
                    title="Card inflows filed to envelopes that never charged the card",
                    detail=(
                        " ".join(uncharged)
                        + " Nothing was riding there to release, so each inflow reduced "
                        "the card's Ready to pay without freeing any envelope's cash — "
                        "the shape a reimbursement or a misfiled deposit makes."
                    ),
                    action=(
                        "Re-file each inflow to the envelope that actually charged the "
                        "card, or leave it and assign the amount to the card. The card's "
                        "Ready to pay breakdown names the months."
                    ),
                    account_ids=sorted(set(uncharged_ids), key=str),
                )
            )
        return findings

    async def _payment_envelope_shadow(
        self, budget_id: uuid.UUID, summary
    ) -> HygieneFinding | None:
        """A spending envelope holding almost exactly a card's missing reserve.

        The migration trap `scripts/repair_card_payment_transfers.py`
        documents: a budget that funded card payments through a hand-made
        envelope ("Sapphire Visa Fund") ends, once payments become transfers, with a
        negative set-aside and a matching surplus in that envelope. Ready to
        Assign is right either way — the two cancel — but it takes one budget
        move to square, and nothing else on any page connects the two numbers.
        """
        categories = {
            c.id: c.name
            for c in await CategoryRepository(self.session).get_all(
                budget_id, include_archived=True
            )
        }
        envelopes = [
            b
            for b in summary.category_balances
            if not b.in_system_group and not b.is_card_payment and b.available > 0
        ]
        lines: list[str] = []
        account_ids: list[uuid.UUID] = []
        for card in summary.cards:
            if card.set_aside >= 0 or card.card_credit > 0:
                continue
            hole = -card.set_aside
            tolerance = max(Decimal("5"), hole * Decimal("0.02"))
            for b in envelopes:
                if abs(b.available - hole) > tolerance:
                    continue
                name = categories.get(b.category_id, "an envelope")
                card_tokens = {w.lower() for w in card.name.split() if len(w) > 2}
                similar = any(w.lower() in card_tokens for w in name.split())
                lines.append(
                    f"{name} holds {b.available} while {card.name}'s Ready to pay is "
                    f"{card.set_aside}" + (" — and the names match." if similar else ".")
                )
                account_ids.append(card.account_id)
        if not lines:
            return None
        return HygieneFinding(
            kind="payment_envelope_shadow",
            title="An envelope holds almost exactly a card's missing reserve",
            detail=(
                " ".join(lines)
                + " This is the shape left behind by funding card payments through an "
                "ordinary envelope: converting the payments to transfers drained the "
                "card's reserve while the envelope kept the money. Ready to Assign is "
                "right either way — the two cancel."
            ),
            action=(
                "Move the envelope's balance to the card: a negative assignment on the "
                "envelope and the same amount assigned to the card, in the same month."
            ),
            account_ids=account_ids,
        )

    async def _money_in_an_archived_envelope_from(
        self, budget_id: uuid.UUID, summary
    ) -> HygieneFinding | None:
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
