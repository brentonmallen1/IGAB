"""A category the server says cannot be filed to, cannot be filed to.

`IS_CATEGORIZABLE` was honoured by five client pickers and by nothing on the
server: `transaction_service` checked only `require_in_budget` and the
card-envelope third of the rule. So the guarantee held exactly as long as every
client surface remembered it, and any other route — a script, a stale build, a
picker written next month — could file a row into an archived envelope.

`card_payment.py` had already written the argument down: *a rule the server
does not enforce is one client away from coming back.* These tests are that
sentence, applied to the whole rule instead of a third of it.

The write side refuses; the read side does not. History filed before a category
was archived stays exactly where it is, because preserving it is the entire
point of archiving rather than deleting.
"""

from datetime import date
from decimal import Decimal

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.card_payment import ensure_payment_category
from igab.services.transaction_service import TransactionCreate, TransactionUpdate

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

D = Decimal
TODAY = date.today()


async def _world(db_session):
    services = make_services(db_session)
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    checking = await create_account(db_session, budget, "Redwood Checking")
    group = await create_category_group(db_session, budget, "Everyday")
    live = await create_category(db_session, budget, group, "Groceries")
    return services, budget, checking, group, live


async def _archive(db_session, obj):
    obj.is_archived = True
    await db_session.flush()


class TestTheWriteSideRefuses:
    async def test_an_archived_category_cannot_be_filed_to(self, db_session):
        services, budget, checking, _group, cat = await _world(db_session)
        await _archive(db_session, cat)

        with pytest.raises(InvariantViolation, match="archived"):
            await services.transactions.create(
                budget.id,
                TransactionCreate(
                    account_id=checking.id, date=TODAY, amount=D("-10.00"), category_id=cat.id
                ),
            )

    async def test_a_category_in_an_archived_group_cannot_either(self, db_session):
        """The group's flag, not the category's. `CategoryRepository.get_all`
        filters the category's `is_archived` and not the group's, so these rows
        reach the client looking ordinary — the server is the only place that
        can tell."""
        services, budget, checking, group, cat = await _world(db_session)
        await _archive(db_session, group)

        with pytest.raises(InvariantViolation, match="archived"):
            await services.transactions.create(
                budget.id,
                TransactionCreate(
                    account_id=checking.id, date=TODAY, amount=D("-10.00"), category_id=cat.id
                ),
            )

    async def test_a_card_envelope_still_names_itself(self, db_session):
        """The rule this one subsumed. Its message was specific and good, and
        a generic 'that category cannot be used' would send someone hunting."""
        services, budget, checking, _group, _cat = await _world(db_session)
        visa = await create_account(db_session, budget, "Visa", account_type="credit_card")
        linked = await ensure_payment_category(db_session, visa)
        assert linked is not None

        with pytest.raises(InvariantViolation, match="payment envelope"):
            await services.transactions.create(
                budget.id,
                TransactionCreate(
                    account_id=checking.id, date=TODAY, amount=D("-10.00"), category_id=linked.id
                ),
            )

    async def test_an_update_cannot_move_a_row_into_an_archived_category(self, db_session):
        """Create is not the only door. `update` carries bulk categorize."""
        services, budget, checking, _group, cat = await _world(db_session)
        txn = await create_transaction(db_session, budget, checking, "-10.00", TODAY)
        await _archive(db_session, cat)

        with pytest.raises(InvariantViolation, match="archived"):
            await services.transactions.update(
                budget.id, txn.id, TransactionUpdate(category_id=cat.id)
            )

    async def test_a_live_category_is_untouched(self, db_session):
        """The control. A guard that refuses everything passes every test
        above and is worthless."""
        services, budget, checking, _group, cat = await _world(db_session)
        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=TODAY, amount=D("-10.00"), category_id=cat.id
            ),
        )
        assert created.category_id == cat.id


class TestTheReadSideDoesNot:
    async def test_history_filed_before_archiving_stays_put(self, db_session):
        """Archiving is not deleting. The row keeps its category, and every
        report still counts it — `category_filters.SPENT_ENVELOPE`."""
        services, budget, checking, _group, cat = await _world(db_session)
        txn = await create_transaction(db_session, budget, checking, "-40.00", TODAY, category=cat)
        await _archive(db_session, cat)

        again = await TransactionRepository(db_session).get(txn.id)
        assert again is not None and again.category_id == cat.id

    async def test_such_a_row_can_still_be_edited_in_place(self, db_session):
        """Only the category is guarded. Fixing a typo in the memo of a row
        that predates the archive must not be collateral damage."""
        services, budget, checking, _group, cat = await _world(db_session)
        txn = await create_transaction(db_session, budget, checking, "-40.00", TODAY, category=cat)
        await _archive(db_session, cat)

        updated = await services.transactions.update(
            budget.id, txn.id, TransactionUpdate(memo="reimbursed")
        )
        assert updated.memo == "reimbursed"
        assert updated.category_id == cat.id


class TestTheGuardReachesWhatTheServerResolves:
    """`require_categorizable` validates the category the *caller* supplied.
    Auto-categorization then resolves a different one, afterwards — from the
    payee's history or from its stored default — and neither path was held to
    the rule the typed path had just been held to.

    Both were already excluding a card's set-aside envelope, for exactly this
    reason: commit 8ac9d15, "Nothing is filed to a card's set-aside envelope".
    Archiving is the same shape of mistake and a quieter one, because an
    archived envelope is off the grid entirely — there is no toggle to find
    the money behind any more.
    """

    async def test_history_in_an_archived_envelope_is_not_inherited(self, db_session):
        services, budget, checking, _group, cat = await _world(db_session)
        payee = await create_payee(db_session, budget, "Blue Bottle")
        await create_transaction(
            db_session, budget, checking, "-12.00", TODAY, category=cat, payee=payee
        )
        await _archive(db_session, cat)

        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=TODAY, amount=D("-12.00"), payee_id=payee.id
            ),
        )
        # Uncategorized, not refused: the user picked a payee, not a category,
        # so the row lands in the needs-a-category pile where they can see it.
        assert created.category_id is None

    async def test_history_in_a_live_envelope_still_is(self, db_session):
        """The guard must not cost auto-categorization its whole job."""
        services, budget, checking, _group, cat = await _world(db_session)
        payee = await create_payee(db_session, budget, "Blue Bottle")
        await create_transaction(
            db_session, budget, checking, "-12.00", TODAY, category=cat, payee=payee
        )

        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=TODAY, amount=D("-12.00"), payee_id=payee.id
            ),
        )
        assert created.category_id == cat.id

    async def test_a_payee_default_pointing_at_an_archived_envelope_is_not_used(self, db_session):
        """The default is a stored pointer, so it outlives what it points at —
        no transaction history is needed to reach this path."""
        services, budget, checking, _group, cat = await _world(db_session)
        payee = await create_payee(db_session, budget, "Blue Bottle")
        payee.default_category_id = cat.id
        await db_session.flush()
        await _archive(db_session, cat)

        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=TODAY, amount=D("-12.00"), payee_id=payee.id
            ),
        )
        assert created.category_id is None

    async def test_a_payee_default_in_an_archived_group_is_not_used_either(self, db_session):
        """The group's flag, not the category's — `IS_CATEGORIZABLE` covers
        both and a hand-rolled `is_archived` check would have covered one."""
        services, budget, checking, group, cat = await _world(db_session)
        payee = await create_payee(db_session, budget, "Blue Bottle")
        payee.default_category_id = cat.id
        await db_session.flush()
        await _archive(db_session, group)

        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=TODAY, amount=D("-12.00"), payee_id=payee.id
            ),
        )
        assert created.category_id is None

    async def test_a_live_payee_default_still_is(self, db_session):
        services, budget, checking, _group, cat = await _world(db_session)
        payee = await create_payee(db_session, budget, "Blue Bottle")
        payee.default_category_id = cat.id
        await db_session.flush()

        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=TODAY, amount=D("-12.00"), payee_id=payee.id
            ),
        )
        assert created.category_id == cat.id

    async def test_a_card_envelope_default_is_still_refused(self, db_session):
        """The narrower rule this replaced. It has to keep holding."""
        services, budget, checking, _group, _cat = await _world(db_session)
        card = await create_account(
            db_session, budget, "Sapphire Visa", account_type="credit_card", on_budget=True
        )
        envelope = await ensure_payment_category(db_session, card)
        assert envelope is not None
        payee = await create_payee(db_session, budget, "Blue Bottle")
        payee.default_category_id = envelope.id
        await db_session.flush()

        created = await services.transactions.create(
            budget.id,
            TransactionCreate(
                account_id=checking.id, date=TODAY, amount=D("-12.00"), payee_id=payee.id
            ),
        )
        assert created.category_id is None
