"""Every liability-classified account carries a Liability row.

Before this, creating an account of type Loan gave you a working ledger and
none of the loan features — no APR, no amortization, no payoff estimate — and
the only thing in the product that mentioned the missing piece was education
copy inside a modal you had to go looking for. The YNAB importer made it the
default outcome: it maps accounts through a type mapping and never created a
liability, so importing a real budget with a mortgage landed you in the dead
end every time.

The fix is structural rather than a prompt. These pin that the row appears on
every path that can make such an account, that it appears empty and inert, and
that nothing quietly removes it again.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from igab.db.models import Liability
from igab.domain.dates import add_months
from igab.repositories.liability_repo import LiabilityRepository
from igab.services.liability_service import (
    LiabilityService,
    ensure_for_account,
    release_for_account,
)

from .factories import (
    create_account,
    create_budget,
    create_category,
    create_category_group,
    create_liability,
    create_liability_snapshot,
    create_transaction,
    create_user,
)

TODAY = date.today()

#: The mortgage ledger `TestConvertingADebtKeepsItsChart` converts: an opening
#: balance a year back, then eleven monthly payments.
#:
#: Defined once because the assertion needs the same dates the fixture writes.
#: **Monthly means `add_months`, not 30 days.** A 30-day step drifts, and in a
#: 28-day February it steps clean over the month: from 30 Jan straight to 1
#: Mar, leaving February with no row at all. `_owed_history` documents that it
#: skips months with no activity ("a gap is not a hole"), so the ledger then
#: produced 11 points where a span-based count predicted 12 — every run on a
#: date whose walk clears February, which is how CI (in UTC) failed while a
#: developer an hour behind UTC saw it pass.
#:
#: Stepping by real months makes the dates land in twelve consecutive months
#: whatever the date is read, so the count below is a literal rather than
#: arithmetic that has to re-derive the bug.
MORTGAGE_LEDGER: list[tuple[date, str]] = [(add_months(TODAY, -12), "-300000.00")] + [
    (add_months(TODAY, -12 + month), "1000.00") for month in range(1, 12)
]

#: Distinct calendar months the ledger above touches — one opening month plus
#: eleven payment months, and exactly the number of monthly points
#: `_owed_history` should produce, since none of them is empty.
MORTGAGE_LEDGER_MONTHS = 12


async def _companion(db_session, account) -> Liability | None:
    """The row linked to this account, deleted or not — the unique constraint
    does not filter on is_deleted, so neither does this."""
    return (
        await db_session.execute(select(Liability).where(Liability.linked_account_id == account.id))
    ).scalar_one_or_none()


class TestEnsureForAccount:
    async def test_creates_an_empty_companion(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )

        created = await ensure_for_account(db_session, loan)

        assert created is not None
        assert created.linked_account_id == loan.id
        assert created.name == "Car Loan"
        # Empty and inert: nothing is computed from absent terms, and a linked
        # row's balance comes from the ledger, not from manual_balance.
        assert created.interest_rate is None
        assert created.minimum_payment is None
        assert created.manual_balance is None

    async def test_credit_cards_get_one_too(self, db_session):
        """Presence, not nagging. A card does have an APR, so the page should
        have a place for it whether or not the number is known."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        card = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )

        created = await ensure_for_account(db_session, card)

        assert created is not None
        # Stored: nothing. The kind comes from the account, so there is no
        # second copy to drift.
        assert created.liability_type is None

    async def test_asset_accounts_get_nothing(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        for account_type in ("checking", "savings", "investment", "other_asset"):
            account = await create_account(
                db_session, budget, f"A {account_type}", account_type=account_type
            )

            assert await ensure_for_account(db_session, account) is None
            assert await _companion(db_session, account) is None

    async def test_is_idempotent(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )

        first = await ensure_for_account(db_session, loan)
        second = await ensure_for_account(db_session, loan)

        # None on the second call, so a caller counting what it made cannot
        # double-count a row that already stood.
        assert second is None
        rows = (
            (
                await db_session.execute(
                    select(Liability).where(Liability.linked_account_id == loan.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1 and rows[0].id == first.id

    async def test_does_not_overwrite_an_existing_one(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Mortgage", account_type="loan", on_budget=False
        )
        existing = await create_liability(
            db_session,
            budget,
            "Maple St Mortgage",
            liability_type="mortgage",
            linked_account_id=loan.id,
            interest_rate=Decimal("6.25"),
            minimum_payment=Decimal("1896.20"),
        )

        await ensure_for_account(db_session, loan)

        assert existing.name == "Maple St Mortgage"
        assert existing.interest_rate == Decimal("6.25")
        assert existing.liability_type == "mortgage"

    async def test_revives_a_soft_deleted_companion(self, db_session):
        """linked_account_id is uniquely constrained without an is_deleted
        filter, so a deleted row still occupies the slot — inserting beside it
        would fail. Reviving is also the truthful outcome: the account still
        exists and still classifies as debt, and the user's terms come back."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        buried = await create_liability(
            db_session,
            budget,
            "Car Loan",
            linked_account_id=loan.id,
            interest_rate=Decimal("4.5"),
            minimum_payment=Decimal("310.00"),
        )
        buried.is_deleted = True
        await db_session.flush()

        revived = await ensure_for_account(db_session, loan)

        assert revived is not None and revived.id == buried.id
        assert revived.is_deleted is False
        assert revived.interest_rate == Decimal("4.5")

    async def test_skips_a_deleted_account(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        loan.is_deleted = True
        await db_session.flush()

        assert await ensure_for_account(db_session, loan) is None


class TestReleaseForAccount:
    async def test_removes_a_companion_nobody_filled_in(self, db_session):
        """Same rule the delete flow applies: only ask about something there is
        something to lose."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        card = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        await ensure_for_account(db_session, card)

        await release_for_account(db_session, card)

        companion = await _companion(db_session, card)
        assert companion is not None and companion.is_deleted is True

    async def test_leaves_a_companion_with_real_terms(self, db_session):
        """Managed debt becoming manually tracked debt is a conversion, and
        converting silently is what this work decided not to do. It stays put
        until the delete dialog can ask."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        await create_liability(
            db_session,
            budget,
            "Car Loan",
            linked_account_id=loan.id,
            interest_rate=Decimal("4.5"),
            minimum_payment=Decimal("310.00"),
        )

        await release_for_account(db_session, loan)

        companion = await _companion(db_session, loan)
        assert companion is not None and companion.is_deleted is False


class TestCreationPaths:
    async def test_creating_a_loan_account_through_the_api(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Car Loan", "account_type": "loan", "on_budget": False},
        )

        assert resp.status_code == 201, resp.text
        liabilities = await LiabilityRepository(db_session).get_all(budget.id)
        assert [item.name for item in liabilities] == ["Car Loan"]
        assert liabilities[0].linked_account_id is not None

    async def test_creating_a_checking_account_creates_nothing(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/accounts",
            json={"name": "Everyday", "account_type": "checking", "on_budget": True},
        )

        assert resp.status_code == 201, resp.text
        assert await LiabilityRepository(db_session).get_all(budget.id) == []

    async def test_retyping_an_asset_into_a_liability(self, api_client, db_session):
        """The account did not exist as debt when it was created, so the
        companion has to follow the type across the line."""
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(db_session, budget, "Card", account_type="checking")

        resp = await api_client.patch(
            f"/api/v1/accounts/{account.id}",
            json={"account_type": "credit_card"},
        )

        assert resp.status_code == 200, resp.text
        assert await _companion(db_session, account) is not None

    async def test_retyping_away_drops_an_empty_companion(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(db_session, budget, "Card", account_type="credit_card")
        await ensure_for_account(db_session, account)

        resp = await api_client.patch(
            f"/api/v1/accounts/{account.id}",
            json={"account_type": "checking"},
        )

        assert resp.status_code == 200, resp.text
        assert await LiabilityRepository(db_session).get_all(budget.id) == []


class TestDeletingACompanionIsRefused:
    """The row belongs to its account now, and everything written after this
    point assumes it exists. Deleting it would put a Loan account back in the
    dead-end state with nothing saying so."""

    async def test_delete_is_409_while_the_account_stands(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        companion = await ensure_for_account(db_session, loan)
        assert companion is not None

        resp = await api_client.delete(f"/api/v1/{budget.id}/liabilities/{companion.id}")

        assert resp.status_code == 409, resp.text
        # The message has to name the action that does work, or a 409 is just
        # a wall.
        assert "account" in resp.json()["detail"].lower()
        assert len(await LiabilityRepository(db_session).get_all(budget.id)) == 1

    async def test_unmanaged_liabilities_still_delete(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        standalone = await create_liability(
            db_session, budget, "Family Loan", manual_balance=Decimal("1200.00")
        )

        resp = await api_client.delete(f"/api/v1/{budget.id}/liabilities/{standalone.id}")

        assert resp.status_code == 204, resp.text

    async def test_a_liability_whose_account_is_gone_still_deletes(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        loan = await create_account(
            db_session, budget, "Old Loan", account_type="loan", on_budget=False
        )
        companion = await ensure_for_account(db_session, loan)
        assert companion is not None
        loan.is_deleted = True
        await db_session.flush()

        resp = await api_client.delete(f"/api/v1/{budget.id}/liabilities/{companion.id}")

        assert resp.status_code == 204, resp.text


class TestTheCompanionChangesNoNumbers:
    async def test_net_worth_does_not_double_count(self, db_session):
        """_unmanaged_liabilities counts only rows with no linked account,
        precisely because managed ones are already counted through theirs. A
        companion is managed, so net worth must not move when it appears."""
        from igab.services.liability_service import LiabilityService

        from .factories import make_services

        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-9000.00", TODAY)
        svc = LiabilityService(
            LiabilityRepository(db_session),
            services.account_repo,
            services.category_repo,
            services.transaction_repo,
        )
        before = await svc.unmanaged_total(budget.id)

        await ensure_for_account(db_session, loan)

        assert await svc.unmanaged_total(budget.id) == before

    async def test_the_debt_becomes_visible_in_the_liabilities_report(self, db_session):
        """The figure that DOES move, and the reason it should: a loan account
        with no companion is absent from the rollup entirely today — its debt
        real, on the ledger, and silently missing from the total."""
        from igab.services.liability_service import LiabilityService

        from .factories import make_services

        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Car Loan", account_type="loan", on_budget=False
        )
        await create_transaction(db_session, budget, loan, "-9000.00", TODAY)
        svc = LiabilityService(
            LiabilityRepository(db_session),
            services.account_repo,
            services.category_repo,
            services.transaction_repo,
        )
        assert (await svc.liabilities_report(budget.id))["total_balance"] == Decimal("0")

        await ensure_for_account(db_session, loan)

        report = await svc.liabilities_report(budget.id)
        assert report["total_balance"] == Decimal("9000.00")
        assert report["liabilities_missing_terms"] == 1


class TestTheImporterPath:
    async def test_a_mapped_loan_account_arrives_with_its_companion(self, db_session):
        """The scenario the loan features were built for and never reached:
        the importer maps accounts through a user-supplied type mapping and
        never created a liability, so importing a budget with a mortgage put
        you in the dead-end state by default."""
        from igab.integrations.ynab.importer import YNABImporter
        from igab.integrations.ynab.models import YNABBudget, YNABTransaction
        from igab.repositories.category_repo import CategoryGroupRepository

        from .factories import make_services

        services = make_services(db_session)
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        importer = YNABImporter(
            session=db_session,
            budget_id=budget.id,
            account_repo=services.account_repo,
            category_group_repo=CategoryGroupRepository(db_session),
            category_repo=services.category_repo,
            payee_repo=services.payee_repo,
            transaction_repo=services.transaction_repo,
            transaction_service=services.transactions,
            assignment_repo=services.assignment_repo,
            account_types={
                "Maple St Mortgage": ("loan", False),
                "Everyday": ("checking", True),
            },
        )

        result = await importer.import_budget(
            YNABBudget(
                transactions=[
                    YNABTransaction(
                        account_name="Maple St Mortgage",
                        date=TODAY,
                        payee="Opening Balance",
                        category_group=None,
                        category=None,
                        memo=None,
                        amount=Decimal("-286000.00"),
                        cleared="cleared",
                    ),
                    YNABTransaction(
                        account_name="Everyday",
                        date=TODAY,
                        payee="Employer",
                        category_group=None,
                        category=None,
                        memo=None,
                        amount=Decimal("3000.00"),
                        cleared="cleared",
                    ),
                ],
            )
        )
        assert result.errors == [], result.errors

        liabilities = await LiabilityRepository(db_session).get_all(budget.id)
        assert [item.name for item in liabilities] == ["Maple St Mortgage"]
        # Empty, so the import invents no terms — but present, so the account
        # page has somewhere to put them.
        assert liabilities[0].interest_rate is None


class TestSnapshotsAndCategoriesCountAsFilledIn:
    async def test_a_companion_with_snapshots_survives_release(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        card = await create_account(db_session, budget, "Visa", account_type="credit_card")
        companion = await ensure_for_account(db_session, card)
        assert companion is not None
        await create_liability_snapshot(db_session, companion, TODAY, Decimal("400.00"))

        await release_for_account(db_session, card)

        # Snapshots are on an unmanaged path, so this is belt and braces —
        # but "untouched" must mean untouched, not "no terms".
        refreshed = await _companion(db_session, card)
        assert refreshed is not None

    async def test_a_companion_with_a_linked_category_survives_release(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        card = await create_account(db_session, budget, "Visa", account_type="credit_card")
        companion = await ensure_for_account(db_session, card)
        assert companion is not None
        group = await create_category_group(db_session, budget, "Debt")
        category = await create_category(db_session, budget, group, "Card Payment")
        category.linked_liability_id = companion.id
        await db_session.flush()

        await release_for_account(db_session, card)

        refreshed = await _companion(db_session, card)
        assert refreshed is not None


class TestLiabilityTypeIsDerivedWhenLinked:
    """`liability_type` said what the linked account's type already said — the
    one genuinely duplicated field in this model. It is now authoritative only
    when there is no account, the same rule `manual_balance` follows.

    That is only lossless because the account-type registry was made specific
    enough to carry a debt's name: mortgage, auto_loan and student_loan sit
    alongside credit_card and a generic loan. Deriving from a registry that
    only knew "loan" would have relabelled every mortgage.
    """

    async def _service(self, db_session):
        from .factories import make_services

        services = make_services(db_session)
        return LiabilityService(
            LiabilityRepository(db_session),
            services.account_repo,
            services.category_repo,
            services.transaction_repo,
        )

    async def test_a_managed_liability_reads_its_account(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        account = await create_account(
            db_session, budget, "Maple St", account_type="mortgage", on_budget=False
        )
        companion = await ensure_for_account(db_session, account)
        assert companion is not None

        svc = await self._service(db_session)

        assert await svc.resolve_type(companion) == "mortgage"

    async def test_the_stored_column_does_not_speak_while_linked(self, db_session):
        """A row carrying a stale value must not contradict its account — that
        contradiction is the reason the field is being retired."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        account = await create_account(
            db_session, budget, "Visa", account_type="credit_card", on_budget=True
        )
        stale = await create_liability(
            db_session, budget, "Visa", liability_type="mortgage", linked_account_id=account.id
        )

        svc = await self._service(db_session)

        assert await svc.resolve_type(stale) == "credit_card"

    async def test_retyping_the_account_moves_the_liability_with_it(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        account = await create_account(
            db_session, budget, "Vehicle Loan", account_type="loan", on_budget=False
        )
        companion = await ensure_for_account(db_session, account)
        assert companion is not None
        svc = await self._service(db_session)
        assert await svc.resolve_type(companion) == "loan"

        from igab.services.account_type_service import apply_type, resolve_type

        type_row = await resolve_type(db_session, budget.id, "auto_loan")
        for field, value in apply_type(type_row, False).items():
            setattr(account, field, value)
        await db_session.flush()

        assert await svc.resolve_type(companion) == "auto_loan"

    async def test_an_unmanaged_liability_keeps_its_own_kind(self, db_session):
        """`personal` and `medical` have no account type, and should not need
        one — nobody keeps a ledger for a dental payment plan."""
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        manual = await create_liability(
            db_session,
            budget,
            "Dental Payment Plan",
            liability_type="medical",
            manual_balance=Decimal("855.00"),
        )

        svc = await self._service(db_session)

        assert await svc.resolve_type(manual) == "medical"

    async def test_a_custom_account_type_answers_as_itself(self, db_session):
        """No mapping table, so a user's own type needs no entry anywhere —
        which is the point of deriving from the registry rather than a literal."""
        from igab.db.models import AccountType
        from igab.services.account_type_service import apply_type, resolve_type

        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        db_session.add(
            AccountType(
                budget_id=budget.id,
                key="heloc",
                label="HELOC",
                classification="liability",
                default_on_budget=False,
                is_system=False,
                sort_order=99,
            )
        )
        await db_session.flush()
        type_row = await resolve_type(db_session, budget.id, "heloc")
        account = await create_account(db_session, budget, "Line of Credit")
        for field, value in apply_type(type_row, False).items():
            setattr(account, field, value)
        await db_session.flush()
        companion = await ensure_for_account(db_session, account)
        assert companion is not None

        svc = await self._service(db_session)

        assert await svc.resolve_type(companion) == "heloc"

    async def test_the_api_reports_the_resolved_kind(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(
            db_session, budget, "Sallie Mae", account_type="student_loan", on_budget=False
        )
        await ensure_for_account(db_session, account)

        resp = await api_client.get(f"/api/v1/{budget.id}/liabilities")

        assert resp.status_code == 200, resp.text
        (body,) = resp.json()
        assert body["liability_type"] == "student_loan"

    async def test_creating_an_unmanaged_liability_still_needs_a_kind(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)

        resp = await api_client.post(
            f"/api/v1/{budget.id}/liabilities",
            json={
                "name": "Family Loan",
                "interest_rate": "4.5",
                "minimum_payment": "150.00",
                "manual_balance": "3600.00",
            },
        )

        assert resp.status_code == 422, resp.text
        assert "type" in resp.json()["detail"].lower()

    async def test_creating_a_managed_liability_does_not_store_one(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(
            db_session, budget, "Maple St", account_type="mortgage", on_budget=False
        )

        resp = await api_client.post(
            f"/api/v1/{budget.id}/liabilities",
            json={
                "name": "Maple St Mortgage",
                "liability_type": "personal",
                "interest_rate": "6.25",
                "minimum_payment": "1896.20",
                "linked_account_id": str(account.id),
            },
        )

        assert resp.status_code == 201, resp.text
        # Sent "personal", stored nothing, reported the account's kind.
        assert resp.json()["liability_type"] == "mortgage"
        stored = (
            await db_session.execute(
                select(Liability).where(Liability.linked_account_id == account.id)
            )
        ).scalar_one()
        assert stored.liability_type is None


class TestDeletingTheAccountBehindADebt:
    """The debt does not stop existing because its ledger did.

    Converting managed → unmanaged is the right default: the balance history is
    worth keeping and a mortgage is not repaid by deleting an account. It must
    not happen silently either way, which is why the disposition is a parameter
    the caller supplies rather than something inferred here.
    """

    async def _account_with_debt(self, db_session, *, terms=True):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        account = await create_account(
            db_session, budget, "Car Loan", account_type="auto_loan", on_budget=False
        )
        await create_transaction(db_session, budget, account, "-9480.00", TODAY)
        companion = await create_liability(
            db_session,
            budget,
            "Car Loan",
            liability_type=None,
            linked_account_id=account.id,
            interest_rate=Decimal("6.25") if terms else None,
            minimum_payment=Decimal("275.00") if terms else None,
        )
        return budget, account, companion

    async def test_keeping_the_debt_freezes_its_balance(self, db_session):
        """The ledger is about to be soft-deleted, so the balance has to be
        captured first — computing it afterwards would freeze a zero and read
        as "paid off"."""
        from igab.repositories.account_repo import AccountRepository

        budget, account, companion = await self._account_with_debt(db_session)

        await AccountRepository(db_session).soft_delete(account.id, liability_disposition="keep")

        assert companion.is_deleted is False
        assert companion.linked_account_id is None
        assert companion.manual_balance == Decimal("9480.00")
        assert companion.interest_rate == Decimal("6.25")

    async def test_keeping_the_debt_gives_it_back_a_kind_of_its_own(self, db_session):
        """It was reading its kind off the account. With the account gone it
        has to carry one again, or the Liabilities report shows a blank."""
        from igab.repositories.account_repo import AccountRepository

        budget, account, companion = await self._account_with_debt(db_session)
        assert companion.liability_type is None

        await AccountRepository(db_session).soft_delete(account.id)

        assert companion.liability_type == "auto"

    async def test_keep_is_the_default(self, db_session):
        from igab.repositories.account_repo import AccountRepository

        budget, account, companion = await self._account_with_debt(db_session)

        await AccountRepository(db_session).soft_delete(account.id)

        assert companion.is_deleted is False

    async def test_deleting_both_removes_the_liability(self, db_session):
        from igab.repositories.account_repo import AccountRepository

        budget, account, companion = await self._account_with_debt(db_session)

        await AccountRepository(db_session).soft_delete(account.id, liability_disposition="delete")

        assert companion.is_deleted is True

    async def test_the_kept_debt_still_reports_its_balance(self, db_session):
        """The point of keeping it: the household still owes this money, and
        the rollup has to keep saying so."""
        from igab.repositories.account_repo import AccountRepository
        from igab.services.liability_service import LiabilityService

        from .factories import make_services

        services = make_services(db_session)
        budget, account, _ = await self._account_with_debt(db_session)
        svc = LiabilityService(
            LiabilityRepository(db_session),
            services.account_repo,
            services.category_repo,
            services.transaction_repo,
        )

        await AccountRepository(db_session).soft_delete(account.id)

        report = await svc.liabilities_report(budget.id, as_of=TODAY)
        (row,) = report["items"]
        assert row["mode"] == "unmanaged"
        assert row["current_balance"] == Decimal("9480.00")

    async def test_an_ordinary_account_is_unaffected(self, db_session):
        from igab.repositories.account_repo import AccountRepository

        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        checking = await create_account(db_session, budget, "Everyday")
        await create_transaction(db_session, budget, checking, "-40.00", TODAY)

        await AccountRepository(db_session).soft_delete(checking.id)

        assert await LiabilityRepository(db_session).get_all(budget.id) == []

    async def test_the_endpoint_defaults_to_keeping_the_debt(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(
            db_session, budget, "Car Loan", account_type="auto_loan", on_budget=False
        )
        await create_transaction(db_session, budget, account, "-9480.00", TODAY)
        await ensure_for_account(db_session, account)

        resp = await api_client.delete(f"/api/v1/accounts/{account.id}")

        assert resp.status_code == 204, resp.text
        (kept,) = await LiabilityRepository(db_session).get_all(budget.id)
        assert kept.linked_account_id is None

    async def test_the_endpoint_honours_an_explicit_delete(self, api_client, db_session):
        budget = await create_budget(db_session, api_client.test_user)
        account = await create_account(
            db_session, budget, "Car Loan", account_type="auto_loan", on_budget=False
        )
        await create_transaction(db_session, budget, account, "-9480.00", TODAY)
        await ensure_for_account(db_session, account)

        resp = await api_client.delete(
            f"/api/v1/accounts/{account.id}", params={"liability": "delete"}
        )

        assert resp.status_code == 204, resp.text
        assert await LiabilityRepository(db_session).get_all(budget.id) == []


class TestConvertingADebtKeepsItsChart:
    """Net worth history is the figure most at risk here, and it fails
    quietly: `_unmanaged_liabilities` reads an unmanaged liability from its
    SNAPSHOTS, while `manual_balance` only answers for today. A conversion that
    sets the balance and nothing else leaves the debt present now and absent
    from every past point — drawing a cliff into the chart that never happened.
    """

    async def _year_of_mortgage(self, db_session):
        user = await create_user(db_session)
        budget = await create_budget(db_session, user)
        loan = await create_account(
            db_session, budget, "Mortgage", account_type="mortgage", on_budget=False
        )
        for when, amount in MORTGAGE_LEDGER:
            await create_transaction(db_session, budget, loan, amount, when)
        companion = await create_liability(
            db_session,
            budget,
            "Mortgage",
            liability_type=None,
            linked_account_id=loan.id,
            interest_rate=Decimal("6.25"),
            minimum_payment=Decimal("1800.00"),
        )
        await db_session.flush()
        return budget, loan, companion

    async def test_the_curve_survives_the_conversion(self, db_session):
        from igab.repositories.account_repo import AccountRepository
        from igab.services.report_service import ReportService

        budget, loan, _ = await self._year_of_mortgage(db_session)
        svc = ReportService(db_session)
        before = [(p["date"], p["net_worth"]) for p in await svc.net_worth_history(budget.id)]

        await AccountRepository(db_session).soft_delete(loan.id, liability_disposition="keep")
        await db_session.flush()

        after = [(p["date"], p["net_worth"]) for p in await svc.net_worth_history(budget.id)]
        assert after == before

    async def test_snapshots_are_written_for_the_whole_ledger(self, db_session):
        from igab.repositories.account_repo import AccountRepository

        budget, loan, companion = await self._year_of_mortgage(db_session)
        assert await LiabilityRepository(db_session).get_snapshots(companion.id) == []

        await AccountRepository(db_session).soft_delete(loan.id)

        snapshots = await LiabilityRepository(db_session).get_snapshots(companion.id)
        assert len(snapshots) == MORTGAGE_LEDGER_MONTHS
        assert snapshots[0].balance == Decimal("300000.00")
        assert snapshots[-1].balance == companion.manual_balance

    async def test_deleting_both_writes_no_snapshots(self, db_session):
        from igab.repositories.account_repo import AccountRepository

        budget, loan, companion = await self._year_of_mortgage(db_session)

        await AccountRepository(db_session).soft_delete(loan.id, liability_disposition="delete")

        assert await LiabilityRepository(db_session).get_snapshots(companion.id) == []

    async def test_a_liabilitys_own_snapshots_win(self, db_session):
        """(liability_id, date) is unique, and a liability that was unmanaged
        before it was linked keeps records of its own. Reconstructing over them
        would both violate the constraint and overwrite the better number."""
        from igab.repositories.account_repo import AccountRepository

        budget, loan, companion = await self._year_of_mortgage(db_session)
        own = await create_liability_snapshot(
            db_session, companion, TODAY.replace(day=1), Decimal("123.45")
        )

        await AccountRepository(db_session).soft_delete(loan.id)

        kept = [
            s
            for s in await LiabilityRepository(db_session).get_snapshots(companion.id)
            if s.date == own.date
        ]
        assert len(kept) == 1 and kept[0].balance == Decimal("123.45")

    async def test_the_kind_is_derived_not_inherited_from_a_stale_column(self, db_session):
        """The c1d9f4b26a83 backfill wrote a coarse 'other' before the kind
        became derived. While linked that value is ignored by definition, so it
        is not evidence — preferring it would turn a mortgage into "Other" on
        the way out."""
        from igab.repositories.account_repo import AccountRepository

        budget, loan, companion = await self._year_of_mortgage(db_session)
        companion.liability_type = "other"  # as the backfill left it
        await db_session.flush()

        await AccountRepository(db_session).soft_delete(loan.id)

        assert companion.liability_type == "mortgage"
