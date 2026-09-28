"""Interest & fees: one envelope per budget, under the credit cards.

Card interest and fees had nowhere to be filed — a transfer is wrong and the
card's own envelope refuses filing — so they sat in "needs a category". The
envelope is an ordinary spending envelope found by key
(`card_payment.CARD_INTEREST_KEY`); what sets it apart is only that the Credit
cards section draws it (`category_filters.CARD_SECTION_CATEGORY`).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from igab.db.models import Category, CategoryGroup
from igab.domain.exceptions import InvariantViolation
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.transaction_repo import TransactionRepository
from igab.sample_budget.card_scenarios import INTEREST_FUNDED, INTEREST_UNFUNDED
from igab.services.card_payment import (
    CARD_INTEREST_KEY,
    CARD_INTEREST_NAME,
    CARD_PAYMENTS_GROUP,
    ensure_interest_envelope,
    ensure_payment_category,
    find_interest_envelope,
)
from igab.services.category_service import CategoryService
from igab.services.integrity_service import IntegrityService
from igab.services.transaction_service import TransactionCreate

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_payee,
    create_transaction,
    create_user,
    make_services,
)
from .test_card_scenarios import MONTH, _budget_with

TODAY = date.today()
D = Decimal


async def _budget(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    return services, budget


async def _card(db_session, budget, name="Sapphire Visa"):
    card = await create_account(db_session, budget, name, account_type="credit_card")
    await ensure_payment_category(db_session, card)
    await db_session.flush()
    return card


async def _keyed(db_session, budget_id) -> list[Category]:
    return list(
        (
            await db_session.execute(
                select(Category).where(
                    Category.budget_id == budget_id,
                    Category.system_key == CARD_INTEREST_KEY,
                    Category.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars()
    )


def _category_service(db_session, services) -> CategoryService:
    return CategoryService(
        db_session,
        CategoryRepository(db_session),
        CategoryGroupRepository(db_session),
        services.budgets,
        TransactionRepository(db_session),
        BudgetAssignmentRepository(db_session),
    )


class TestMadeWithTheFirstCard:
    async def test_the_first_card_makes_it_in_the_card_group(self, db_session):
        _, budget = await _budget(db_session)
        await _card(db_session, budget)

        [envelope] = await _keyed(db_session, budget.id)
        group = await db_session.get(CategoryGroup, envelope.category_group_id)
        assert envelope.name == CARD_INTEREST_NAME
        assert group is not None and group.name == CARD_PAYMENTS_GROUP
        assert envelope.linked_account_id is None
        assert envelope.is_archived is False

    async def test_a_second_card_makes_nothing_extra(self, db_session):
        _, budget = await _budget(db_session)
        await _card(db_session, budget, "Sapphire Visa")
        [first] = await _keyed(db_session, budget.id)
        await _card(db_session, budget, "Harborstone Card")

        assert [c.id for c in await _keyed(db_session, budget.id)] == [first.id]

    async def test_a_checking_account_makes_none(self, db_session):
        _, budget = await _budget(db_session)
        checking = await create_account(db_session, budget, "Checking")
        await ensure_payment_category(db_session, checking)

        assert await _keyed(db_session, budget.id) == []

    async def test_found_by_key_after_a_rename(self, db_session):
        _, budget = await _budget(db_session)
        await _card(db_session, budget)
        [envelope] = await _keyed(db_session, budget.id)
        envelope.name = "Card interest"
        await db_session.flush()

        again = await ensure_interest_envelope(db_session, budget.id)

        assert again.id == envelope.id
        assert len(await _keyed(db_session, budget.id)) == 1

    async def test_it_adopts_the_users_own_envelope_in_the_card_group(self, db_session):
        """Made before this existed, holding money and history: stamped with
        the key rather than collided with."""
        _, budget = await _budget(db_session)
        group = await create_category_group(db_session, budget, CARD_PAYMENTS_GROUP)
        mine = await create_category(db_session, budget, group, "Interest and Fees")

        await _card(db_session, budget)

        [envelope] = await _keyed(db_session, budget.id)
        assert envelope.id == mine.id
        assert envelope.name == "Interest and Fees", "adopted, not renamed"

    async def test_a_namesake_in_another_group_is_left_alone(self, db_session):
        """Only the card group is adopted from: a user's "Interest & fees"
        under Bills is their own envelope, and the section would steal it."""
        _, budget = await _budget(db_session)
        bills = await create_category_group(db_session, budget, "Bills")
        theirs = await create_category(db_session, budget, bills, CARD_INTEREST_NAME)

        await _card(db_session, budget)

        [envelope] = await _keyed(db_session, budget.id)
        assert envelope.id != theirs.id
        await db_session.refresh(theirs)
        assert theirs.system_key is None

    async def test_an_archived_one_stays_archived(self, db_session):
        _, budget = await _budget(db_session)
        await _card(db_session, budget)
        [envelope] = await _keyed(db_session, budget.id)
        envelope.is_archived = True
        await db_session.flush()

        await _card(db_session, budget, "Harborstone Card")

        [again] = await _keyed(db_session, budget.id)
        assert again.id == envelope.id and again.is_archived is True


class TestItLivesInTheCardSection:
    async def test_served_in_card_section_for_it_and_for_card_envelopes_only(self, db_session):
        services, budget = await _budget(db_session)
        card = await _card(db_session, budget)
        bills = await create_category_group(db_session, budget, "Bills")
        rent = await create_category(db_session, budget, bills, "Rent")
        await db_session.flush()

        by_id = {c.id: c for c in await services.category_repo.get_all(budget.id)}
        [interest] = await _keyed(db_session, budget.id)
        linked = await services.category_repo.get_by_linked_account(card.id)
        assert linked is not None

        assert by_id[interest.id].in_card_section is True
        assert by_id[linked.id].in_card_section is True
        assert by_id[rent.id].in_card_section is False

    async def test_it_is_an_ordinary_envelope_everywhere_but_placement(self, db_session):
        """Offered, filed to, funded — unlike the card's own envelope."""
        services, budget = await _budget(db_session)
        await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)

        served = await services.category_repo.get(interest.id)

        assert served is not None
        assert served.is_assignable is True
        assert served.is_fundable is True
        assert served.is_categorizable is True

    async def test_the_card_group_stays_card_only(self, db_session):
        """So "Credit Card Payments" never draws as a grid header with
        Interest & fees under it."""
        services, budget = await _budget(db_session)
        await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)

        group = await services.category_group_repo.get(interest.category_group_id)

        assert group is not None and group.is_card_only is True

    async def test_an_ordinary_envelope_in_the_group_still_draws_it(self, db_session):
        services, budget = await _budget(db_session)
        await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)
        group = await services.category_group_repo.get(interest.category_group_id)
        assert group is not None
        await create_category(db_session, budget, group, "Annual dues")

        again = await services.category_group_repo.get(group.id)

        assert again is not None and again.is_card_only is False

    async def test_a_reorder_may_leave_it_out_like_a_card_envelope(self, db_session):
        """The grid cannot drag what it does not draw."""
        services, budget = await _budget(db_session)
        await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)
        group = await services.category_group_repo.get(interest.category_group_id)
        assert group is not None
        dues = await create_category(db_session, budget, group, "Annual dues")
        levy = await create_category(db_session, budget, group, "Levy")

        await services.category_repo.reorder(group.id, [levy.id, dues.id])

        await db_session.refresh(levy)
        await db_session.refresh(dues)
        assert levy.sort_order < dues.sort_order

    async def test_the_integrity_check_stays_quiet(self, db_session):
        """The pairing check matched the card group by name and would have
        called this "a card's envelope that points at no live card"."""
        _, budget = await _budget(db_session)
        await _card(db_session, budget)

        report = await IntegrityService(db_session).run(budget.id)

        pairing = next(c for c in report.checks if c.name == "card_payment_envelope_pairing")
        assert pairing.passed, pairing.details


class TestKeptWhileACardNeedsIt:
    async def test_delete_is_refused_while_a_card_exists(self, db_session):
        services, budget = await _budget(db_session)
        await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)
        service = _category_service(db_session, services)

        preview = await service.preview_delete(budget.id, [interest.id], MONTH)
        assert preview.blocked_by == [
            "'Interest & fees' is where card interest is filed; archive it instead."
        ]
        with pytest.raises(InvariantViolation, match="archive it instead"):
            await service.delete_categories(budget.id, [interest.id], month=MONTH)

    async def test_delete_is_allowed_once_no_card_is_left(self, db_session):
        services, budget = await _budget(db_session)
        card = await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)
        card.is_deleted = True
        await db_session.flush()

        await _category_service(db_session, services).delete_categories(
            budget.id, [interest.id], month=MONTH
        )

        assert await find_interest_envelope(db_session, budget.id) is None

    async def test_it_may_be_archived(self, db_session):
        services, budget = await _budget(db_session)
        await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)

        await _category_service(db_session, services).archive_categories(
            budget.id, [interest.id], month=MONTH
        )

        await db_session.refresh(interest)
        assert interest.is_archived is True

    async def test_a_move_to_another_group_is_refused(self, db_session):
        _, budget = await _budget(db_session)
        await _card(db_session, budget)
        [interest] = await _keyed(db_session, budget.id)
        bills = await create_category_group(db_session, budget, "Bills")

        with pytest.raises(InvariantViolation, match="cannot be moved"):
            CategoryService.require_movable(interest, bills.id)
        # Staying put is not a move.
        CategoryService.require_movable(interest, interest.category_group_id)

    async def test_the_api_refuses_the_move_and_allows_the_rename(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        await db_session.commit()
        created = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Sapphire Visa", "account_type": "credit_card"},
        )
        assert created.status_code == 201, created.text
        listed = (await api_client.get(f"/api/v1/{budget.id}/categories")).json()
        [interest] = [c for c in listed if c["name"] == CARD_INTEREST_NAME]
        group = await api_client.post(
            f"/api/v1/{budget.id}/category-groups", json={"name": "Bills"}
        )
        assert group.status_code == 201, group.text

        moved = await api_client.patch(
            f"/api/v1/categories/{interest['id']}",
            json={"category_group_id": group.json()["id"]},
        )
        renamed = await api_client.patch(
            f"/api/v1/categories/{interest['id']}", json={"name": "Card interest"}
        )

        assert moved.status_code == 400, moved.text
        assert "cannot be moved" in moved.json()["detail"]
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "Card interest"
        assert renamed.json()["in_card_section"] is True


class TestInterestFilesItself:
    """The last auto-filing fallback in `TransactionService.create`."""

    async def _world(self, db_session):
        services, budget = await _budget(db_session)
        card = await _card(db_session, budget)
        checking = await create_account(db_session, budget, "Checking")
        [interest] = await _keyed(db_session, budget.id)
        return services, budget, card, checking, interest

    def _synced(self, account, amount, payee, description=None, n=1):
        """A feed row, spelled the way `SimpleFINService._import_feed_row`
        spells it."""
        return TransactionCreate(
            account_id=account.id,
            date=TODAY,
            amount=Decimal(amount),
            payee_name=payee,
            import_description=description,
            sync_id=f"feed-{payee}-{amount}-{n}",
            sync_source="simplefin",
            cleared="cleared",
            approved=False,
            bank_posted_date=TODAY,
            bank_amount=Decimal(amount),
            bank_payee=payee,
            auto_categorize=True,
        )

    async def test_a_synced_interest_charge_files_itself(self, db_session):
        services, budget, card, _, interest = await self._world(db_session)

        row = await services.transactions.create(
            budget.id, self._synced(card, "-12.34", "INTEREST CHARGE ON PURCHASES")
        )

        assert row.category_id == interest.id
        assert row.approved is False, "auto-filed rows still ask to be approved"

    async def test_the_bank_description_is_read_too(self, db_session):
        services, budget, card, _, interest = await self._world(db_session)

        row = await services.transactions.create(
            budget.id, self._synced(card, "-39.00", "Sapphire Bank", description="LATE FEE")
        )

        assert row.category_id == interest.id

    async def test_a_renamed_envelope_still_catches_it(self, db_session):
        services, budget, card, _, interest = await self._world(db_session)
        interest.name = "Card interest"
        await db_session.flush()

        row = await services.transactions.create(
            budget.id, self._synced(card, "-5.00", "Annual Fee")
        )

        assert row.category_id == interest.id

    async def test_not_on_a_checking_account(self, db_session):
        services, budget, _, checking, _ = await self._world(db_session)

        row = await services.transactions.create(
            budget.id, self._synced(checking, "-12.00", "Late fee")
        )

        assert row.category_id is None

    async def test_not_an_inflow(self, db_session):
        """A reversed fee coming back is not a charge to file."""
        services, budget, card, _, _ = await self._world(db_session)

        row = await services.transactions.create(budget.id, self._synced(card, "39.00", "Late fee"))

        assert row.category_id is None

    async def test_not_a_payment_or_a_merchant(self, db_session):
        services, budget, card, _, _ = await self._world(db_session)

        payment = await services.transactions.create(
            budget.id, self._synced(card, "-50.00", "Online payment, thank you")
        )
        bakery = await services.transactions.create(
            budget.id, self._synced(card, "-8.00", "Fee Fi Fo Fum Bakery")
        )

        assert payment.category_id is None
        assert bakery.category_id is None

    async def test_not_into_an_archived_envelope(self, db_session):
        services, budget, card, _, interest = await self._world(db_session)
        interest.is_archived = True
        await db_session.flush()

        row = await services.transactions.create(
            budget.id, self._synced(card, "-12.00", "Interest charge")
        )

        assert row.category_id is None

    async def test_payee_history_answers_first(self, db_session):
        """Once a user files one elsewhere, that choice is what repeats."""
        services, budget, card, _, _ = await self._world(db_session)
        bills = await create_category_group(db_session, budget, "Bills")
        dues = await create_category(db_session, budget, bills, "Card dues")
        payee = await create_payee(db_session, budget, "Annual Fee")
        await create_transaction(
            db_session, budget, card, "-95.00", date(2026, 1, 5), category=dues, payee=payee
        )
        await db_session.flush()

        row = await services.transactions.create(
            budget.id, self._synced(card, "-95.00", "Annual Fee", n=2)
        )

        assert row.category_id == dues.id

    async def test_not_when_the_caller_asked_for_no_auto_filing(self, db_session):
        """Rows from before an account joined the budget arrive unfiled."""
        services, budget, card, _, _ = await self._world(db_session)
        data = self._synced(card, "-12.00", "Interest charge")
        data.auto_categorize = False

        row = await services.transactions.create(budget.id, data)

        assert row.category_id is None


class TestTheScenariosReadOnTheEnvelope:
    """The card scenarios pin the CARD; these pin the envelope beside it."""

    async def test_unfunded_interest_reads_red(self, db_session):
        services, budget, _ = await _budget_with(db_session, INTEREST_UNFUNDED)
        [interest] = await _keyed(db_session, budget.id)

        summary = await services.budgets.get_budget_summary(budget.id, MONTH)
        row = next(b for b in summary.category_balances if b.category_id == interest.id)

        assert row.available == D("-15")
        assert row.credit_overspent == D("15"), "spent on a card, so it rides rather than charges"

    async def test_a_red_interest_and_fees_is_covered_by_cover_overspent(self, db_session):
        """The server half of the Overspent chip's promise
        (`BudgetTable.overspent.test.tsx` is the client half): a red Interest &
        fees is in the served count and total, in Cover Overspent's list, and
        covering it clears it."""
        services, budget, _ = await _budget_with(db_session, INTEREST_UNFUNDED)
        [interest] = await _keyed(db_session, budget.id)

        summary = await services.budgets.get_budget_summary(budget.id, MONTH)
        red = [b.category_id for b in summary.category_balances if b.available < 0]
        assert red == [interest.id]
        assert summary.overspent_count == 1
        assert summary.total_overspent == D("15")

        preview = await services.budgets.cover_overspent_preview(budget.id, MONTH)
        assert [(i.category_id, i.proposed_addition) for i in preview.items] == [
            (interest.id, D("15"))
        ]
        await services.budgets.cover_overspent_apply(
            budget.id, MONTH, [(i.category_id, i.proposed_addition) for i in preview.items]
        )

        after = await services.budgets.get_budget_summary(budget.id, MONTH)
        row = next(b for b in after.category_balances if b.category_id == interest.id)
        assert row.available == D("0")
        assert after.total_overspent == D("0")
        assert after.overspent_count == 0
        # Funding it in the month it ended short retires the ride: the card
        # now has the 15 set aside against the 15 it owes.
        card = next(c for c in after.cards if c.name == INTEREST_UNFUNDED.card)
        assert (card.set_aside, card.uncovered) == (D("15"), D("0"))

    async def test_funded_interest_reads_spent(self, db_session):
        services, budget, _ = await _budget_with(db_session, INTEREST_FUNDED)
        [interest] = await _keyed(db_session, budget.id)

        summary = await services.budgets.get_budget_summary(budget.id, MONTH)
        row = next(b for b in summary.category_balances if b.category_id == interest.id)

        assert row.available == D("0")

    async def test_both_share_the_one_envelope(self, db_session):
        _, budget, applied = await _budget_with(db_session, INTEREST_FUNDED, INTEREST_UNFUNDED)

        [interest] = await _keyed(db_session, budget.id)
        assert all(a.categories[CARD_INTEREST_NAME].id == interest.id for a in applied)
        count = (
            await db_session.execute(
                select(func.count())
                .select_from(Category)
                .where(Category.budget_id == budget.id, Category.name == CARD_INTEREST_NAME)
            )
        ).scalar_one()
        assert count == 1
