"""The export has to read back, and it has to agree with itself.

Most of this harness already existed, which is what makes the export
trustworthy rather than merely plausible:

- `export_consistency` checks a parsed export against *itself* — Available ==
  prior Available + Assigned + Activity down each category's months, and each
  Plan Activity cell equal to the register rows filed to that category that
  month. Both are properties of the file alone.
- `check_parity` recomputes Available from IGAB's own data and compares it to
  the file's Available column.

Real YNAB exports get a tolerance from these, because YNAB jitters figures per
cell. Ours is generated, so it gets none: **exactly zero** violations, and
**zero** parity differences.

The fixture is the sample budget — thirteen months, transfers, splits, a card,
an intentional overspend — because a one-month budget proves nothing about
carry-over, which is the half of the plan that can actually be wrong.
"""

import io
import json
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from igab.integrations.ynab.oracle import export_consistency
from igab.integrations.ynab.parity import check_parity
from igab.integrations.ynab.parser import YNABParser
from igab.repositories.category_repo import CategoryRepository
from igab.services.budget_export import NOT_CARRIED

from .factories import create_budget, create_user, make_services
from .test_sample_budget import ANCHOR, generate_sample


@pytest.fixture
async def sample(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user, "Household")
    await generate_sample(db_session, budget)
    return budget


async def _export(api_client, budget_id) -> bytes:
    resp = await api_client.get(f"/api/v1/budgets/{budget_id}/export?format=ynab")
    assert resp.status_code == 200, resp.text
    return resp.content


def _parse(body: bytes, tmp_path: Path):
    """Through the real parser, from a real file on disk — the same path an
    upload takes."""
    path = tmp_path / "export.zip"
    path.write_bytes(body)
    return YNABParser().parse_zip(path)


class TestItReadsBack:
    async def test_the_parser_takes_it_with_no_errors(self, api_client, sample, tmp_path):
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        assert parsed.errors == []
        assert parsed.transactions
        assert parsed.plan_rows

    async def test_the_members_are_named_the_way_the_parser_looks_for_them(
        self, api_client, sample
    ):
        with zipfile.ZipFile(io.BytesIO(await _export(api_client, sample.id))) as archive:
            names = archive.namelist()
        assert any(n.lower().endswith("- register.csv") for n in names)
        assert any(n.lower().endswith("- plan.csv") for n in names)

    async def test_transfers_come_back_as_transfers(self, api_client, sample, tmp_path):
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        transfers = [t for t in parsed.transactions if t.payee.startswith("Transfer : ")]
        assert transfers, "the sample budget has transfers; the export lost them"

    async def test_splits_are_reassembled(self, api_client, sample, tmp_path):
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        splits = [t for t in parsed.transactions if t.splits]
        assert splits, "the sample budget has splits; the export lost them"
        for txn in splits:
            assert txn.amount == sum(leg.amount for leg in txn.splits)

    async def test_cleared_state_survives(self, api_client, sample, tmp_path):
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        states = {t.cleared for t in parsed.transactions}
        assert "reconciled" in states or "cleared" in states


class TestItAgreesWithItself:
    async def test_carryover_and_activity_are_exactly_consistent(
        self, api_client, sample, tmp_path
    ):
        """Stricter than a real YNAB export gets: ours is generated, not
        jittered per cell, so anything above zero is our bug."""
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        result = export_consistency(parsed)

        assert result.carryover_rows_checked > 0, "no months to check — the fixture is too small"
        assert result.carryover_rows_violating == 0
        assert result.activity_cells_checked > 0
        assert result.activity_cells_disagreeing == 0


class TestWhatACellCannotHonestlySay:
    async def test_a_card_payment_envelope_writes_no_activity(
        self, api_client, db_session, sample, tmp_path
    ):
        """The column means "the register rows filed to this category this
        month". A card payment is a transfer, so no row is filed there —
        IGAB's figure is a computed set-aside. Writing it would be a false
        claim; writing zero would be a different one."""
        parsed = _parse(await _export(api_client, sample.id), tmp_path)

        # Ask IGAB which envelope that is rather than guessing from the name:
        # "Mortgage Payment" is an ordinary category and does have activity.
        services = make_services(db_session)
        summary = await services.budgets.get_budget_summary(sample.id, ANCHOR.replace(day=1))
        card_ids = {b.category_id for b in summary.category_balances if b.is_card_payment}
        assert card_ids, "the sample budget has a card; its envelope is missing"
        named = await CategoryRepository(db_session).get_all_with_group_names(
            sample.id, include_hidden=True
        )
        card_names = {c.name for c, _ in named if c.id in card_ids}

        payment_rows = [r for r in parsed.plan_rows if r.category in card_names]
        assert payment_rows
        assert all(r.activity is None for r in payment_rows)
        # The figure that IS real still travels: what the card has set aside.
        # (Assigned stays zero — IGAB computes card set-asides rather than
        # having anyone assign to the envelope.)
        assert any(r.available not in (None, Decimal("0")) for r in payment_rows)

    async def test_the_readme_says_why(self, api_client, sample):
        with zipfile.ZipFile(io.BytesIO(await _export(api_client, sample.id))) as archive:
            readme = archive.read("README.txt").decode()
        assert "payment envelope" in readme


class TestItAgreesWithTheBudgetItCameFrom:
    async def test_parity_is_zero_for_every_month(self, api_client, db_session, sample, tmp_path):
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        services = make_services(db_session)
        category_repo = CategoryRepository(db_session)

        months = sorted({row.month for row in parsed.plan_rows})
        assert len(months) > 6, "carry-over is the half that can be wrong; check several months"

        for month in months:
            report = await check_parity(
                services.budgets,
                category_repo,
                sample.id,
                parsed,
                month,
                accounts=None,
                credit_card_accounts=[],
            )
            assert report.top_differences == [], f"{month}: {report.top_differences}"
            assert report.categories_differing == 0, month


class TestItSaysWhatItDropped:
    async def test_the_readme_names_everything_not_carried(self, api_client, sample):
        with zipfile.ZipFile(io.BytesIO(await _export(api_client, sample.id))) as archive:
            readme = archive.read("README.txt").decode()
        for name in NOT_CARRIED:
            assert name in readme, f"README does not mention {name}"
        assert "snapshot" in readme.lower(), "the README must point at the lossless option"

    async def test_the_manifest_says_it_in_a_machine_readable_way(self, api_client, sample):
        with zipfile.ZipFile(io.BytesIO(await _export(api_client, sample.id))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        assert manifest["shape"] == "ynab"
        assert manifest["not_carried"] == NOT_CARRIED
        assert manifest["row_counts"]["register"] > 0


class TestAccountsMember:
    async def test_the_real_account_types_travel(self, api_client, sample, tmp_path):
        """Without this member, build_ynab_preview guesses types from account
        names and a re-import becomes a re-mapping chore."""
        with zipfile.ZipFile(io.BytesIO(await _export(api_client, sample.id))) as archive:
            accounts = archive.read("Accounts.csv").decode()
        assert "Account,Type,Classification,On Budget,Closed,Note" in accounts
        assert "checking" in accounts

    async def test_a_re_import_gets_the_real_types_rather_than_a_guess(
        self, api_client, sample, tmp_path
    ):
        """The whole point of the member. Without it build_ynab_preview reads
        the account's name and guesses, which is right often and not always."""
        from igab.api.v1.imports import build_ynab_preview

        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        assert parsed.account_types, "Accounts.csv was not read back"

        preview = build_ynab_preview(parsed)
        for account in preview.accounts:
            expected_type, expected_on_budget = parsed.account_types[account.name]
            assert account.suggested_type == expected_type, account.name
            assert account.suggested_on_budget == expected_on_budget, account.name
            # Nothing to review: these are not guesses.
            assert account.needs_review is False, account.name

    async def test_a_file_without_the_member_still_guesses(self, api_client, sample, tmp_path):
        """A real YNAB export has no Accounts.csv, and must keep working."""
        from igab.api.v1.imports import build_ynab_preview

        body = await _export(api_client, sample.id)
        stripped = io.BytesIO()
        with (
            zipfile.ZipFile(io.BytesIO(body)) as source,
            zipfile.ZipFile(stripped, "w") as target,
        ):
            for item in source.namelist():
                if item != "Accounts.csv":
                    target.writestr(item, source.read(item))

        parsed = _parse(stripped.getvalue(), tmp_path)
        assert parsed.account_types == {}
        assert build_ynab_preview(parsed).accounts

    async def test_the_core_reader_ignores_it(self, api_client, sample, tmp_path):
        """An additive member must not disturb the parser — that is what makes
        the extras safe to add later."""
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        assert parsed.errors == []


class TestTheEndpoint:
    async def test_an_unknown_format_is_refused(self, api_client, sample):
        resp = await api_client.get(f"/api/v1/budgets/{sample.id}/export?format=qif")
        assert resp.status_code == 400
        assert "ynab" in resp.json()["detail"]

    async def test_a_member_may_export(self, api_client, db_session, sample):
        """A member can already export the register through
        /{budget_id}/reports/export; this is the same data in a better shape."""
        from .factories import add_budget_member

        member = await create_user(db_session)
        await add_budget_member(db_session, sample, member)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: member
        resp = await api_client.get(f"/api/v1/budgets/{sample.id}/export?format=ynab")
        assert resp.status_code == 200

    async def test_a_stranger_gets_a_404(self, api_client, db_session, sample):
        stranger = await create_user(db_session)

        from igab.dependencies import get_current_user
        from igab.main import app

        app.dependency_overrides[get_current_user] = lambda: stranger
        resp = await api_client.get(f"/api/v1/budgets/{sample.id}/export?format=ynab")
        assert resp.status_code == 404

    async def test_an_empty_budget_exports_an_empty_but_valid_file(
        self, api_client, db_session, tmp_path
    ):
        """No months, no rows — and still a file the parser reads, rather than
        a 500 on the way to one."""
        empty = await create_budget(db_session, api_client.test_user, "Brand New")
        parsed = _parse(await _export(api_client, empty.id), tmp_path)
        assert parsed.transactions == []
        assert parsed.plan_rows == []


class TestAmountsAndDates:
    async def test_amounts_are_split_across_outflow_and_inflow(self, api_client, sample):
        with zipfile.ZipFile(io.BytesIO(await _export(api_client, sample.id))) as archive:
            register = next(n for n in archive.namelist() if n.endswith("- Register.csv"))
            content = archive.read(register).decode()
        header, *rows = content.splitlines()
        assert "Outflow,Inflow" in header
        # Never both on one row: the parser reads inflow - outflow.
        for row in rows[:50]:
            cells = row.split(",")
            outflow, inflow = cells[-3], cells[-2]
            assert not (outflow and inflow), row

    async def test_dates_are_the_first_format_the_parser_tries(self, api_client, sample, tmp_path):
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        dates = {t.date for t in parsed.transactions}
        assert dates
        assert min(dates) >= ANCHOR - timedelta(days=800)
        assert all(isinstance(d, date) for d in dates)

    async def test_no_amount_is_written_as_a_float(self, api_client, sample, tmp_path):
        parsed = _parse(await _export(api_client, sample.id), tmp_path)
        for txn in parsed.transactions:
            assert isinstance(txn.amount, Decimal)
