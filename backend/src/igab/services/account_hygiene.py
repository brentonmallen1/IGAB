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

from igab.db.models import Account, Asset, Liability, Transaction
from igab.domain.card_timeline import card_timeline, first_breach
from igab.domain.cards import SetAsideState, card_reserve, receivable_ledgers, riding_series
from igab.domain.import_mapping import _TRACKED_HINTS, _matches, _normalize_for_match
from igab.domain.matching import DATE_WINDOW_DAYS
from igab.domain.transfers import LegPair, PairableLeg, pair_legs
from igab.guide.detection import budget_service_from
from igab.repositories.category_repo import CategoryRepository
from igab.repositories.txn_filters import (
    AFTER_BUDGET_START,
    CARD_ROW_FILED_AS_INCOME,
    LEAF,
    NOT_DELETED,
    ON_BUDGET_ACCOUNT,
    PAIRABLE_LEG,
    POSTED,
    UNPAIRED_TRANSFER_LEG,
)
from igab.utils.clock import today_utc

#: Months without a posted transaction before an open account reads as dormant.
#: Matches the import step's threshold so the two never disagree about the same
#: account.
DORMANT_AFTER_MONTHS = 12
#: A card with nothing posted for this long is at risk of being closed by
#: its issuer. Ninety days is shorter than dormancy on purpose: the fix is a
#: coffee, and the cost of missing it is a closed line.
CARD_QUIET_DAYS = 90

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

#: Months before a stated asset value reads as stale. 12, matching BOTH
#: existing staleness precedents — DORMANT_AFTER_MONTHS above and the Guide's
#: STALE_EXTERNAL_MONTHS (guide/concepts.py) — so a third staleness rule
#: cannot drift from the other two.
STALE_ASSET_VALUE_MONTHS = 12


@dataclass
class FindingItem:
    """One thing a finding is about — an account, an envelope, one row.

    Amounts and dates travel raw and the client formats them. Every finding
    used to write its figures into a sentence here, which is how "58.6800" and
    "-100.0000" reached the screen: a string the server composed can never
    follow the user's currency format, and a list written as prose cannot be
    scanned.
    """

    label: str
    amount: Decimal | None = None
    #: A month the item is about ("since September 2026").
    month: date | None = None
    #: A day the item is about (the date of a row).
    day: date | None = None
    #: One short clause of context — never a figure; figures go in `amount`.
    note: str | None = None
    #: What to do about this item when it differs from the finding's action.
    fix: str | None = None
    #: Where the item leads: an account's register, and a row to highlight.
    account_id: uuid.UUID | None = None
    transaction_id: uuid.UUID | None = None
    #: The rows a bulk action on this item would touch, in the order that
    #: action expects — for unlinked card payments, (outflow, inflow).
    transaction_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class HygieneFinding:
    #: Stable key, so the frontend can route the fix without parsing prose.
    kind: str
    title: str
    #: One sentence: what is wrong. Read first; must stand without `why`.
    summary: str
    #: What to do about it, in the user's terms. One or two short sentences.
    action: str
    items: list[FindingItem] = field(default_factory=list)
    #: The reasoning, for whoever wants it. Drawn collapsed.
    why: str | None = None
    #: Accounts this is about, most-relevant first.
    account_ids: list[uuid.UUID] = field(default_factory=list)
    #: For findings about a valued Asset, which is not an account — the panel
    #: routes these to /assets/{id} instead.
    asset_ids: list[uuid.UUID] = field(default_factory=list)
    #: For findings that lead to transactions rather than to an account.
    transaction_count: int = 0


@dataclass
class HygieneReport:
    findings: list[HygieneFinding]

    @property
    def clean(self) -> bool:
        return not self.findings


@dataclass
class CardPaymentPair:
    """One unlinked card payment: the `pair_legs` verdict and its two rows."""

    pair: LegPair
    outflow: Transaction
    inflow: Transaction
    card_leg: Transaction
    cash_leg: Transaction


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
        # Which envelopes are receivable ledgers rather than funds — read once
        # here, because two card detectors ask and both must give the same
        # answer about the same category.
        ledgers = self._ledger_categories(summary, walk)
        # Named before the per-envelope inflow findings: a card this one
        # already explains (its item names the envelope the refund went to)
        # is not described a second time in a second vocabulary.
        negative = await self._card_reserve_went_negative(budget_id, summary, walk, ledgers)
        named = set(negative.account_ids) if negative is not None else set()
        findings = [
            # Order is the ranking. On-budget-but-tracked leads because it is
            # the only one here that corrupts a number the user reads daily:
            # to_be_assigned is total account balance minus category balances,
            # so a house inside the budget poisons every envelope figure.
            await self._tracked_name_on_budget(accounts),
            await self._liability_with_positive_balance(accounts),
            # Same class of problem as the two above, and the same reason it
            # ranks here: it corrupts to_be_assigned, from an account the user
            # cannot see to check.
            await self._closed_account_still_holds_money(accounts),
            await self._asset_beside_asset_account(budget_id, accounts),
            await self._unpaired_transfer_legs(budget_id),
            await self._unlinked_card_payments(budget_id),
            negative,
            await self._card_debt_predates_budget(budget_id, summary, walk),
            *(await self._misfiled_card_inflows(budget_id, walk, ledgers, named)),
            await self._categorized_tracking_rows(budget_id),
            await self._card_rows_filed_as_income(budget_id),
            await self._dormant_open_accounts(accounts, budget_id),
            await self._card_no_activity(accounts),
            await self._stale_companion_liabilities(budget_id, accounts),
            await self._money_in_an_archived_envelope_from(budget_id, summary),
            await self._stale_asset_values(budget_id),
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
            summary="Named like something you own outright — a house, a car — but on budget.",
            items=[FindingItem(label=a.name, account_id=a.id) for a in hits],
            action="Open the account's settings and turn off On budget.",
            why=(
                "An on-budget balance counts toward Ready to Assign, so a house or a car "
                "inside the budget inflates every envelope figure."
            ),
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
            summary="A debt account holding money is usually something you own, typed as a debt.",
            items=[
                FindingItem(
                    label=a.name, amount=Decimal(str(balances.get(a.id, 0.0))), account_id=a.id
                )
                for a in hits
            ],
            action="Check the balance. If the account is something you own, change its type.",
            why=(
                "Debt accounts are subtracted from net worth, so an asset typed as a debt "
                "moves net worth by twice its balance. An overpaid loan is real, which is "
                "why this is a suggestion and not a fix."
            ),
            account_ids=[a.id for a in hits],
        )

    async def _closed_account_still_holds_money(
        self, accounts: list[Account]
    ) -> HygieneFinding | None:
        """A closed ON-BUDGET account with a balance left in it.

        Closed and on-budget is not a contradiction, and forcing them apart
        would be worse than the gap this closes: `on_budget` is read at query
        time by the activity classifier, so flipping it on close would
        reclassify every historical row on the account — spending from an old
        checking account would become activity inside a tracked account, and
        transfers into it would become saving. Reports would change because
        someone tidied up. The commonest closed account in any budget is a
        checking account closed when its owner changed banks, and it was on
        budget for its whole life.

        What IS contradictory is a closed on-budget account holding money.
        Closing moves none, so the balance goes on funding Ready to Assign
        from an account that is no longer in the sidebar. The cards half of
        this was already handled — `get_budget_summary` keeps a closed card's
        row until its balance and set-aside both reach zero — and cash
        accounts had nothing at all.

        Cards are left to that mechanism rather than reported twice: a closed
        card with a balance is already on the budget page, tagged, with the
        actions next to it.
        """
        cash = [
            a for a in accounts if a.is_closed and a.on_budget and a.classification != "liability"
        ]
        balances = await self._balances([a.id for a in cash])
        # Any real amount, not SIGN_MISMATCH_FLOOR: that floor exists to keep a
        # sign test quiet on small balances, and this is not a sign test. A
        # tenner stranded in a closed account is still a tenner backing
        # envelopes from somewhere nobody can see. Cents guard against float
        # dust from the sum.
        hits = [a for a in cash if abs(balances.get(a.id, 0.0)) >= 0.01]
        if not hits:
            return None
        return HygieneFinding(
            kind="closed_account_holds_money",
            title=(
                f"{len(hits)} closed account{'s' if len(hits) > 1 else ''} still "
                f"hold{'' if len(hits) > 1 else 's'} money"
            ),
            summary=(
                "Closing an account moves no money, so this still counts toward Ready to Assign."
            ),
            items=[
                FindingItem(
                    label=a.name, amount=Decimal(str(balances.get(a.id, 0.0))), account_id=a.id
                )
                for a in hits
            ],
            action=(
                "Record the transfer that emptied it. If the account is something you own "
                "rather than cash, turn off On budget instead."
            ),
            why=(
                "The balance funds Ready to Assign from an account that is no longer in "
                "your sidebar. It is usually a transfer that never got recorded."
            ),
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
            summary="Each names another account as its payee, but nothing links back.",
            action=(
                "Match them up links every one whose other side is unmistakable. Open "
                "what is left to pick its partner."
            ),
            why=(
                "Balances are right either way. Unlinked, these can read as income or "
                "spending in reports instead of money moving between your own accounts. "
                "It is usually what an account left out of an import leaves behind."
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
        pairs = await self.unlinked_card_payment_pairs(budget_id)
        if not pairs:
            return None
        accounts = {a.id: a for a in await self._accounts(budget_id)}
        category_names = {
            c.id: c.name
            for c in await CategoryRepository(self.session).get_all(
                budget_id, include_archived=True
            )
        }
        items: list[FindingItem] = []
        for pair in pairs:
            card_leg, cash_leg = pair.card_leg, pair.cash_leg
            filed = category_names.get(cash_leg.category_id) if cash_leg.category_id else None
            source = accounts[cash_leg.account_id].name
            items.append(
                FindingItem(
                    label=accounts[card_leg.account_id].name,
                    amount=abs(card_leg.amount),
                    day=card_leg.date,
                    note=f"from {source}" + (f", filed to {filed}" if filed else ""),
                    account_id=card_leg.account_id,
                    transaction_id=card_leg.id,
                    transaction_ids=[pair.outflow.id, pair.inflow.id],
                )
            )
        card_ids = list(dict.fromkeys(p.card_leg.account_id for p in pairs))
        n = len(pairs)
        return HygieneFinding(
            kind="unlinked_card_payments",
            title=f"{n:,} card payment{'s' if n != 1 else ''} not linked",
            summary=(
                "A payment onto a card and the matching debit from your own account, "
                "never joined as one transfer."
            ),
            items=items,
            action=("Link them — all at once here, or one at a time from the card's register."),
            why=(
                "Only a linked transfer counts as paying the card: until then its Set "
                "aside is not spent, the payment reads as a credit from nowhere, and an "
                "envelope on the other side counts it as spending. Linking clears that "
                "envelope, so it gets the money back and the card's Set aside falls by the "
                "same amount — move it to the card afterwards. Balances are right either way."
            ),
            account_ids=card_ids,
            transaction_count=n,
        )

    async def unlinked_card_payment_pairs(self, budget_id: uuid.UUID) -> list["CardPaymentPair"]:
        """The pairs `_unlinked_card_payments` reports, as rows.

        Public because the bulk link reads the same list: the pairs a person
        confirmed must be the pairs this finds, decided once — the link
        endpoint refuses any pair not in it rather than trusting the client.
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
                        # History from before an account joined the budget is
                        # opening position, and pairing it does harm: on a
                        # real budget all nine "unlinked payments" predated
                        # their cards' start dates, and linking them drove five
                        # cards' Set aside down by thousands while the money
                        # went back into envelopes that had been archived.
                        AFTER_BUDGET_START,
                        Transaction.date >= cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return []

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
        out: list[CardPaymentPair] = []
        for pair in (*confident, *review):
            outflow, inflow = by_id[pair.outflow_id], by_id[pair.inflow_id]
            # A payment is money arriving ON the card. The reverse — a charge
            # on the card beside a deposit elsewhere — is a cash advance or a
            # coincidence, and calling it a payment would tell the user to
            # link a charge as if it paid the card down.
            if inflow.account_id not in cards:
                continue
            card_leg, cash_leg = inflow, outflow
            out.append(CardPaymentPair(pair, outflow, inflow, card_leg, cash_leg))
        out.sort(key=lambda p: (p.card_leg.date, p.card_leg.id))
        return out

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

        Cash accounts are deliberately excluded, and so are balance-adjustment
        rows on the cards themselves — the two exclusions and their shared
        rationale live on `txn_filters.CARD_ROW_FILED_AS_INCOME`, which the
        repair script reads too so the two cannot disagree about what counts.
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.budget_id == budget_id, CARD_ROW_FILED_AS_INCOME)
        )
        count = result.scalar_one()
        if not count:
            return None
        return HygieneFinding(
            kind="card_rows_filed_as_income",
            title=f"{count:,} card charge{'s' if count != 1 else ''} filed as income",
            summary="A charge on a card filed to an income category reaches no envelope.",
            action=(
                "Give them a real envelope, such as Interest or Bank Fees. Leaving them "
                "uncategorized is also fine."
            ),
            why=(
                "The card's balance moves and the debt lands in Uncovered, but nothing in "
                "the budget names the spending. Interest charges get here on their own "
                "when a payee's history is bank interest."
            ),
            transaction_count=int(count),
        )

    def _ledger_categories(self, summary, walk) -> set[uuid.UUID]:
        """The budget's receivable ledgers — categories run as a running tab
        for someone else's spending rather than as a fund.

        The sweep is `domain.cards.receivable_ledgers` and the rule inside it
        is `residual_is_pass_through`; this only supplies the two inputs. It
        is the SAME call the budget summary makes to decide each card's
        `set_aside_state`, off the same two inputs, so a settle-up cannot
        read as normal on the budget page and as a defect here.

        `walk.assigned_ever` rather than a query of this service's own: the
        test is "never assigned, in any month", the walk already read every
        assignment the budget has, and a second read is a second chance to
        bound it differently.

        A category the summary did not carry is not a ledger — nothing here
        knows what it holds, and silence is the wrong way to be wrong.
        """
        return receivable_ledgers(
            walk.assigned_ever,
            {balance.category_id: balance.available for balance in summary.category_balances},
        )

    #: The Set aside states this finding has something to say about: below
    #: zero, on a card that is not in credit, and not explained by somebody
    #: else's settle-up. The classification itself is served
    #: (`domain/cards.py` `set_aside_state`) — this check used to re-derive
    #: it from `set_aside`, `card_credit` and its own pass over
    #: `residual_by_pair`, which is two implementations of one rule sitting
    #: either side of an API boundary.
    _REPORTABLE_STATES = frozenset(
        {
            SetAsideState.REFUND_OUTRAN_ENVELOPE,
            SetAsideState.SETTLED_ELSEWHERE,
            SetAsideState.RIDE_UNFUNDED,
            SetAsideState.PAID_AHEAD,
            # More than one cause and none covers it: at least part of the
            # shortfall is not a settle-up, so it is worth reading. A card a
            # ledger merely touched must not hide behind the bookkeeping —
            # `test_a_shortfall_only_partly_explained_by_a_ledger_still_reports`.
            SetAsideState.MIXED,
            # Overdrawn by a move, not a payment. Real, and the remedy is
            # to put the money back — worth a line.
            SetAsideState.MOVED_OUT,
        }
    )

    async def _card_reserve_went_negative(
        self, budget_id: uuid.UUID, summary, walk, ledgers: set[uuid.UUID]
    ) -> HygieneFinding | None:
        """A card's Set aside below zero while the card is not in credit.

        A legitimate position, not an integrity failure — the reserve is
        deliberately unfloored (domain/cards.py `CardReserve`) — but on a
        card that still owes money it always has a cause worth reading, and
        the row itself only shows the current figure. This names WHEN it
        crossed and which leg did it, out of the same walk the row is served
        from (`domain/card_timeline.py`).

        **Which cards qualify is not decided here.** `SETTLED_BY_OTHERS` is
        left alone because a ledger settles onto its card every month, so its
        residual drives Set aside down by construction — beside a debt that
        fell with it, and with nothing to re-file or assign. That used to be
        a second pass over `residual_by_pair` written at this call site; it
        now comes off the same served state the budget page reads, so the two
        pages cannot describe one card differently.
        """
        categories = {
            c.id: c.name
            for c in await CategoryRepository(self.session).get_all(
                budget_id, include_archived=True
            )
        }
        items: list[FindingItem] = []
        for card in summary.cards:
            if card.set_aside_state not in self._REPORTABLE_STATES:
                continue
            reserve = card_reserve(walk.funding, card.account_id)
            breach = first_breach(
                card_timeline(
                    reserve,
                    {},
                    riding_series(walk.funding, card.account_id),
                    start=(walk.anchor.openings.opening_month if walk.anchor is not None else None),
                )
            )
            # The envelopes a refund raised instead of this card: named, so
            # the fix says where the money is rather than "an envelope".
            refunded_into = sorted(
                categories.get(cat_id, "an envelope")
                for (cat_id, card_id), series in walk.funding.residual_by_pair.items()
                if card_id == card.account_id
                and cat_id not in ledgers
                and sum(series.values(), Decimal("0")) > 0
            )
            note, fix = self._negative_set_aside_story(card.set_aside_state, refunded_into)
            items.append(
                FindingItem(
                    label=card.name,
                    amount=card.set_aside,
                    month=breach.month if breach is not None else None,
                    note=note,
                    fix=fix,
                    account_id=card.account_id,
                )
            )
        if not items:
            return None
        count = len(items)
        return HygieneFinding(
            kind="card_reserve_went_negative",
            title=f"{count} card{'s' if count != 1 else ''} with Set aside below zero",
            summary="Something took more out of these cards' Set aside than was ever put in.",
            items=items,
            action="Each line says what to do. The card's row on the budget page shows the months.",
            why=(
                "Set aside is the money reserved to pay a card. Below zero, the card has "
                "used money the budget never reserved for it — a payment ahead of the "
                "budget, or a refund that went to an envelope instead."
            ),
            account_ids=[i.account_id for i in items if i.account_id is not None],
        )

    @staticmethod
    def _negative_set_aside_story(
        state: SetAsideState, refunded_into: list[str]
    ) -> tuple[str, str]:
        """What happened to a card below zero, and what fixes it — per state.

        Keyed on the served `set_aside_state`, the same classification the
        card's own row reads, so this panel and the budget page cannot give one
        card two different causes. Never a figure in the text: the item's
        amount is the figure, formatted by the client.
        """
        where = ", ".join(refunded_into) if refunded_into else "an envelope"
        stories = {
            SetAsideState.PAID_AHEAD: (
                "a payment paid more than was set aside for it",
                "Assign this much to the card. Ready to Assign already accounts for it.",
            ),
            SetAsideState.REFUND_OUTRAN_ENVELOPE: (
                f"a refund went to {where} instead of the card",
                f"Move the refund from {where} to the card.",
            ),
            SetAsideState.RIDE_UNFUNDED: (
                "an overspent month rode onto this card and was never funded",
                "Assign this much to the card, or fund the month that overspent.",
            ),
            SetAsideState.SETTLED_ELSEWHERE: (
                "an overspent month was shared across cards, and this card took part",
                "Assign this much to the card.",
            ),
            SetAsideState.MOVED_OUT: (
                "money was moved out of the card's envelope",
                "Move it back to the card.",
            ),
            SetAsideState.MIXED: (
                "more than one cause",
                "Open the card's Set aside breakdown on the budget page to see each one.",
            ),
        }
        return stories.get(state, ("", "Open the card's Set aside breakdown on the budget page."))

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

        An anchored budget never fires this: the anchor IS the "budget start"
        this finding's action text used to ask the user to declare — history
        before it is opening position by construction, and the walk never
        reserves against it in the first place.

        An account's `budget_start_date` is NOT that. It narrows only
        `NEEDS_CATEGORY` — the card walk reads every row — so the action once
        told a user to set a start date their card already had, and nothing
        moved. The action says what does work: assigning to the card.
        """
        if walk.anchor is not None:
            return None
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

        items: list[FindingItem] = []
        for card in summary.cards:
            if card.uncovered <= 0:
                continue
            charged = first_charge.get(card.account_id)
            reserved = first_reserving.get(card.account_id)
            if charged is None or reserved is None or charged >= reserved:
                continue
            items.append(
                FindingItem(
                    label=card.name,
                    amount=card.uncovered,
                    note=(
                        f"charged since {charged:%B %Y}, nothing set aside until {reserved:%B %Y}"
                    ),
                    account_id=card.account_id,
                )
            )
        if not items:
            return None
        count = len(items)
        return HygieneFinding(
            kind="card_debt_predates_budget",
            title=f"{count} card{'s' if count != 1 else ''} carrying debt from before the budget",
            summary="Debt the budget never set money aside for. It reads as Uncovered.",
            items=items,
            action="Assign toward it on the card as you pay it down.",
            why=(
                "Spending from before the budget reserved nothing, so paying that debt "
                "spends money no envelope set aside — which is what pushes Set aside below "
                "zero. Assigning to the card is how paying off old debt is budgeted. An "
                "account's budget start date does not change this: it only stops older "
                "rows asking for a category."
            ),
            account_ids=[i.account_id for i in items if i.account_id is not None],
        )

    async def _misfiled_card_inflows(
        self,
        budget_id: uuid.UUID,
        walk,
        ledgers: set[uuid.UUID],
        named: set[uuid.UUID],
    ) -> list[HygieneFinding | None]:
        """Card inflows that drained a reserve without releasing anything.

        Exposure is per (category, card) — deliberately, see domain/cards.py —
        so such an inflow releases nothing and reduces the card's reserve
        outright (`residual_by_pair`). Two findings, because the remedies
        differ: an envelope that never charged THIS card points at a refund or
        a reimbursement filed to an envelope that was not its charge's; one
        that DOES charge this card but produced residual in two or more months
        carries a recurring inflow stream that has cumulatively outrun its
        charges — a partner's repayments, or payments arriving from outside
        the budget.

        There used to be a third: an envelope whose charges were on a
        DIFFERENT card, read as "this inflow belongs on that card". It was
        a guess from where the envelope's other spending sat, and a real
        budget disproved it — a refund of a doubled charge on the same card,
        filed to an envelope that happened to charge another card, was told to
        move to that other card's register. Where the envelope's spending
        sits says nothing about where a refund belongs.

        A card `named` by the negative-Set-aside finding is left out of the
        uncharged finding: that finding's item already names the envelope the
        refund went to and says to move it, and a second finding about the
        same money in other words is the doubling that made this panel hard to
        read. The recurring finding still names it — a stream is a different
        story with a different remedy (record it as a transfer).

        A pair whose envelope is a **receivable ledger** — never assigned to,
        holding nothing — is skipped by both: see
        `domain.cards.residual_is_pass_through`. Such a category is a running
        tab settled onto the card every month, so its residual is the half of
        an offsetting pair whose other half is a card payment that
        deliberately never happened, and every remedy these findings offer
        would break a budget being kept correctly.

        On an anchored budget the walk starts at the import boundary, so
        these totals cover post-anchor months only — and a refund of a
        pre-anchor charge legitimately lands as residual there (the accepted
        attribution coarsening; see domain/cards.py's anchor section).

        The recurring finding exists because the others used to skip any pair
        that had ever charged the card, on an existence test. The pair reserve
        ratchets negative once inflows overtake charges (`reserved[pair]` is
        uncapped, domain/cards.py), so exactly the histories with the LARGEST
        recurring residual — 42 straight months, on the budget that motivated
        the card probe — were the ones no detector could see.
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

        uncharged: list[FindingItem] = []
        recurring: list[FindingItem] = []
        for (cat_id, card_id), series in walk.funding.residual_by_pair.items():
            total = sum(series.values(), Decimal("0"))
            if total <= 0:
                continue
            if cat_id in ledgers:
                # A running tab settled onto the card, not an envelope that
                # lost money. Nothing here has a remedy.
                continue
            item = FindingItem(
                label=categories.get(cat_id, "An envelope"),
                amount=total,
                note=f"on {names.get(card_id, 'a card')}",
                account_id=card_id,
            )
            if charged(cat_id, card_id):
                # A one-month residual on a charging pair is an ordinary
                # refund overshoot; two or more is a stream.
                if len(series) >= 2:
                    item.note = f"on {names.get(card_id, 'a card')}, over {len(series)} months"
                    recurring.append(item)
                continue
            if card_id not in named:
                uncharged.append(item)

        def cards(items: list[FindingItem]) -> list[uuid.UUID]:
            return sorted({i.account_id for i in items if i.account_id is not None}, key=str)

        findings: list[HygieneFinding | None] = []
        if uncharged:
            findings.append(
                HygieneFinding(
                    kind="residual_on_uncharged_category",
                    title="Card refunds filed to envelopes that never charged the card",
                    summary=(
                        "These envelopes gained money from a card that they never spent on, "
                        "and the card's Set aside fell by the same amount."
                    ),
                    items=sorted(uncharged, key=lambda i: (i.note or "", i.label)),
                    action=(
                        "Move each amount from the envelope to the card, or re-file the "
                        "inflow to the envelope that made the charge."
                    ),
                    why=(
                        "A refund gives money back to the envelope it is filed to. When "
                        "that envelope never charged this card, nothing was set aside to "
                        "release, so the card's Set aside drops by the whole amount while "
                        "the envelope keeps it."
                    ),
                    account_ids=cards(uncharged),
                )
            )
        if recurring:
            findings.append(
                HygieneFinding(
                    kind="recurring_card_residual",
                    title="Recurring inflows are draining a card's Set aside",
                    summary=(
                        "Inflows filed to these envelopes have added up to more than they "
                        "ever charged on the card."
                    ),
                    items=sorted(recurring, key=lambda i: (i.note or "", i.label)),
                    action=(
                        "If it is a payment from outside the budget, or someone paying "
                        "their share, record it as a transfer. Otherwise move the amount to "
                        "the card."
                    ),
                    why=(
                        "Each envelope does charge this card, but once its inflows outrun "
                        "its charges every further inflow lowers the card's Set aside while "
                        "the envelope keeps the money."
                    ),
                    account_ids=cards(recurring),
                )
            )
        return findings

    async def _money_in_an_archived_envelope_from(
        self, budget_id: uuid.UUID, summary
    ) -> HygieneFinding | None:
        """Money sitting in an envelope the budget no longer draws.

        Archiving refuses to leave a balance behind — `CategoryService.
        archive_categories` blocks on it and the dialog says which envelope to
        empty first. Balances still get here — archived before that rule, an
        import that brings a hidden category in archived, activity dated into
        an archived envelope — and the finding does not guess which: it once
        told a user "these predate that rule" about an envelope that had money
        assigned the same month.

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
        return HygieneFinding(
            kind="money_in_an_archived_envelope",
            title=(
                f"{len(stranded)} archived envelope{'s' if len(stranded) != 1 else ''} "
                f"still hold{'' if len(stranded) != 1 else 's'} money"
            ),
            summary=(
                "Archived envelopes are not shown on the budget, so this money counts but "
                "cannot be seen or moved there."
            ),
            items=sorted(
                (
                    FindingItem(label=archived[b.category_id].name, amount=b.available)
                    for b in stranded
                ),
                key=lambda i: i.label,
            ),
            action=(
                "On the budget, open See archived, restore the envelope and move its money. "
                "You can archive it again afterwards."
            ),
            why="Nothing is lost: the money still counts toward Ready to Assign.",
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
            summary=(
                "Off-budget activity is not budget spending, so these categories count nowhere."
            ),
            action="Remove the categories clears them all in one undoable step.",
            why=(
                "The budget and every report leave them out. They arrive with an import, "
                "a sync that learned the category from the payee, or an account moved off "
                "budget later. Amounts, dates and accounts are untouched by the fix."
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
            summary=f"Nothing has posted in over {DORMANT_AFTER_MONTHS} months.",
            items=[
                FindingItem(
                    label=a.name, day=last_seen[a.id], note="last activity", account_id=a.id
                )
                for a in hits
            ],
            action="Close the ones you have finished with. You can reopen any of them later.",
            why=(
                "Closing keeps every transaction — history, reports and net worth are "
                "untouched. It only takes the account out of pickers and filters."
            ),
            account_ids=[a.id for a in hits],
        )

    async def _card_no_activity(self, accounts: list[Account]) -> HygieneFinding | None:
        """An open card with nothing posted for CARD_QUIET_DAYS.

        Issuers close cards that sit unused, and a closed card shortens the
        credit history and shrinks the total limit — both count against the
        score. A small recurring charge keeps it alive. Only cards that HAVE
        posted something count; a card just added is not quiet, it is new.
        """
        cards = [a for a in accounts if not a.is_closed and a.account_type == "credit_card"]
        if not cards:
            return None
        cutoff = today_utc() - timedelta(days=CARD_QUIET_DAYS)
        rows = await self.session.execute(
            select(Transaction.account_id, func.max(Transaction.date))
            .where(Transaction.account_id.in_([a.id for a in cards]), NOT_DELETED, POSTED)
            .group_by(Transaction.account_id)
        )
        last_seen: dict[uuid.UUID, date] = {aid: seen for aid, seen in rows.all()}
        hits = [a for a in cards if last_seen.get(a.id) and last_seen[a.id] < cutoff]
        if not hits:
            return None
        return HygieneFinding(
            kind="card_no_activity",
            title=(
                f"{len(hits)} card{'s' if len(hits) > 1 else ''} not used in {CARD_QUIET_DAYS} days"
            ),
            summary="Issuers close idle cards, which can lower your credit score.",
            items=[
                FindingItem(label=a.name, day=last_seen[a.id], note="last used", account_id=a.id)
                for a in hits
            ],
            action="Put a small recurring charge on it, or close it on your own terms.",
            why=(
                "A closed card shortens your credit history and shrinks your total limit. "
                "One small recurring charge, paid in full, keeps it open."
            ),
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
            summary="Payoff records for accounts that are no longer debts.",
            items=[
                FindingItem(label=liability.name, account_id=liability.linked_account_id)
                for liability in stale
            ],
            action="Delete them from the Liabilities page.",
            why=(
                "Usually the account's type was corrected after an import. They count "
                "nowhere, but they read as debts you do not have."
            ),
            account_ids=[
                liability.linked_account_id for liability in stale if liability.linked_account_id
            ],
        )

    async def _stale_asset_values(self, budget_id: uuid.UUID) -> HygieneFinding | None:
        """A stated value is the app's record of when it was told, and it
        cannot refresh itself. Past a year it is probably not the number the
        household would say today — and it is moving net worth UP, the
        dangerous direction for a stale figure."""
        cutoff = today_utc() - timedelta(days=STALE_ASSET_VALUE_MONTHS * 30)
        result = await self.session.execute(
            select(Asset)
            .where(
                Asset.budget_id == budget_id,
                Asset.is_deleted == False,  # noqa: E712
                Asset.value_as_of.is_not(None),
                Asset.value_as_of < cutoff,
            )
            .order_by(Asset.value_as_of)
        )
        stale = list(result.scalars().all())
        if not stale:
            return None
        return HygieneFinding(
            kind="stale_asset_value",
            title=f"{'A stated value is' if len(stale) == 1 else 'Stated values are'} "
            f"over {STALE_ASSET_VALUE_MONTHS} months old",
            summary="IGAB cannot refresh a value you entered, and these still count in net worth.",
            items=[
                FindingItem(label=a.name, amount=a.manual_value, day=a.value_as_of, note="valued")
                for a in stale
            ],
            action="Open each asset and record what it is worth today.",
            asset_ids=[a.id for a in stale],
        )

    async def _asset_beside_asset_account(
        self, budget_id: uuid.UUID, accounts: list[Account]
    ) -> HygieneFinding | None:
        """The double-count suspect: a valued Asset AND an asset-classified
        tracking account that look like the same thing. Net worth counts a
        house once through the account ledger and once through the value
        series, and nothing can prove they are one house — but a shared name
        is exactly the "probably wrong, not provably" this service exists
        for."""
        result = await self.session.execute(
            select(Asset).where(
                Asset.budget_id == budget_id,
                Asset.is_deleted == False,  # noqa: E712
            )
        )
        assets = list(result.scalars().all())
        if not assets:
            return None
        candidates = [
            a
            for a in accounts
            if a.classification == "asset" and not a.on_budget and not a.is_closed
        ]
        suspects: list[tuple[Asset, Account]] = []
        for asset in assets:
            asset_words = {w for w in asset.name.lower().split() if len(w) >= 4}
            for account in candidates:
                account_words = {w for w in account.name.lower().split() if len(w) >= 4}
                if asset_words & account_words:
                    suspects.append((asset, account))
                    break
        if not suspects:
            return None
        return HygieneFinding(
            kind="asset_beside_asset_account",
            title="A valued asset may double-count an account",
            summary=(
                "A stated value and a tracking account that look like the same thing — "
                "net worth counts both."
            ),
            items=[
                FindingItem(label=asset.name, note=f"and the account {account.name}")
                for asset, account in suspects
            ],
            action="Keep one: delete the stated asset, or close the account.",
            asset_ids=[a.id for a, _ in suspects],
            account_ids=[acc.id for _, acc in suspects],
        )
