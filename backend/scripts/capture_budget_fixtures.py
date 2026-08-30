"""Freeze one budget's export and snapshot as a compatibility fixture.

A format with no frozen fixture has no compatibility guarantee. These files
are what `tests/integration/test_import_compatibility.py` reads: proof that a
file written today still imports, and still means the same numbers, after the
schema moves under it.

    python scripts/capture_budget_fixtures.py --new
    python scripts/capture_budget_fixtures.py --version v1-2026-08

**Never regenerate an existing fixture. Add a new one.**

That is the whole discipline, and it is enforced rather than requested: the
script refuses to write into a directory that already exists. Regenerating is
how a backwards-compatibility suite goes green forever while testing nothing,
and it is always the tempting fix when the test goes red, because the diff
looks like noise. It is not noise. It is the file saying the format changed.

Add a directory whenever `format_version`, a member name, or a column set
changes — those are the only three things that can break a reader.

The budget is generated, never captured: `SampleBudgetGenerator` at the full
tier gives splits, transfers, off-budget accounts, a credit card, hidden
categories, targets, tags, scheduled transactions and liabilities, with no
real person anywhere near it (CLAUDE.md — this repository is public).
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from igab.domain.snapshot_format import VERSION  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
EXPORTS = FIXTURES / "exports"
SNAPSHOTS = FIXTURES / "snapshots"
EXPECTED = EXPORTS / "expected"

#: A fixed anchor, so a captured fixture is the same file whoever runs this
#: and whenever. A moving "today" would make every regeneration a real diff
#: and hide the format changes this corpus exists to surface.
ANCHOR = date(2026, 8, 1)


def _migrate(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    # env.py reads igab.config.settings, not the ini — so the environment is
    # where the URL has to go, and it must be set before that import happens.
    os.environ["DATABASE_URL"] = database_url
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(config, "head")


def default_version() -> str:
    return f"v{VERSION}-{datetime.now(tz=UTC):%Y-%m}"


async def build(session: AsyncSession):
    """A full-tier sample budget, owned by a throwaway user."""
    from igab.db.models import Budget, User
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.category_repo import (
        BudgetAssignmentRepository,
        CategoryGroupRepository,
        CategoryRepository,
    )
    from igab.repositories.liability_repo import LiabilityRepository
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.reconciliation_repo import ReconciliationRepository
    from igab.repositories.scheduled_transaction_repo import ScheduledTransactionRepository
    from igab.repositories.tag_repo import TagRepository, seed_system_tags
    from igab.repositories.target_repo import TargetRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.sample_budget.generator import SampleBudgetGenerator
    from igab.services.account_type_service import ensure_account_types_seeded
    from igab.services.budget_provisioning import grant_owner

    user = User(email="fixtures@example.invalid", password_hash="x" * 60)
    session.add(user)
    await session.flush()
    budget = Budget(user_id=user.id, name="Sample Household", currency_code="USD")
    session.add(budget)
    await session.flush()
    grant_owner(session, budget.id, user.id)
    await ensure_account_types_seeded(session, budget.id)
    await seed_system_tags(session, budget.id)

    generator = SampleBudgetGenerator(
        session,
        budget.id,
        account_repo=AccountRepository(session),
        category_group_repo=CategoryGroupRepository(session),
        category_repo=CategoryRepository(session),
        payee_repo=PayeeRepository(session),
        transaction_repo=TransactionRepository(session),
        assignment_repo=BudgetAssignmentRepository(session),
        tag_repo=TagRepository(session),
        target_repo=TargetRepository(session),
        scheduled_repo=ScheduledTransactionRepository(session),
        reconciliation_repo=ReconciliationRepository(session),
        liability_repo=LiabilityRepository(session),
        tier="full",
    )
    await generator.generate(anchor=ANCHOR)
    await session.flush()
    return budget


async def capture(version: str, database_url: str) -> None:
    export_dir = EXPORTS / version
    snapshot_dir = SNAPSHOTS / version
    expected_path = EXPECTED / f"{version}.json"

    for path in (export_dir, snapshot_dir, expected_path):
        if path.exists():
            raise SystemExit(
                f"{path} already exists.\n\n"
                "NEVER REGENERATE AN EXISTING FIXTURE. Add a new one:\n"
                "    python scripts/capture_budget_fixtures.py --new\n\n"
                "A frozen fixture is a record of what the format meant when it "
                "was written. Rewriting it is how a compatibility suite goes "
                "green forever while testing nothing."
            )

    # Migrated, not create_all'd: a real snapshot records the revision that
    # produced it, and that string is what check_compatibility reads to decide
    # whether a file predates a meaning change. A fixture with a blank
    # revision cannot exercise the guarantee this corpus exists to give.
    _migrate(database_url)
    engine = create_async_engine(database_url)

    # A half-written capture must not survive: it would leave directories that
    # the "never regenerate" guard then refuses to write over, so the next
    # attempt is blocked by the wreckage of the last one.
    written: list[Path] = []

    try:
        await _write(engine, export_dir, snapshot_dir, expected_path, written)
    except BaseException:
        import shutil

        for path in written:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        raise
    finally:
        await engine.dispose()
    print(f"Wrote {export_dir}, {snapshot_dir} and {expected_path}")


async def _write(engine, export_dir, snapshot_dir, expected_path, written) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        from igab.repositories.category_repo import CategoryRepository
        from igab.services.budget_export import export_budget_ynab
        from igab.services.budget_snapshot import export_budget_snapshot

        budget = await build(session)
        services = _services(session)

        export_dir.mkdir(parents=True)
        snapshot_dir.mkdir(parents=True)
        EXPECTED.mkdir(parents=True, exist_ok=True)
        written += [export_dir, snapshot_dir, expected_path]

        export_path = export_dir / "sample-full.igab-export.zip"
        with export_path.open("wb") as handle:
            await export_budget_ynab(
                session,
                services,
                CategoryRepository(session),
                budget.id,
                handle,
                app_version="fixture",
                exported_at=f"{ANCHOR.isoformat()}T00:00:00+00:00",
            )

        with (snapshot_dir / "sample-full.igab.zip").open("wb") as handle:
            await export_budget_snapshot(
                session,
                budget.id,
                handle,
                app_version="fixture",
                alembic_revision=await _revision(session),
            )

        # The contract is what the FILE means, so it is recorded from a budget
        # imported out of it — not from the budget it was written from. The
        # two are not the same: an export cannot carry a card's set-aside
        # envelope, and recording the source would freeze a number no reader
        # of this file can ever produce.
        imported_id = await _import_export(session, export_path)
        expected_path.write_text(
            json.dumps(await _expected(session, _services(session), imported_id), indent=2) + "\n"
        )


def _services(session: AsyncSession):
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.budget_move_repo import BudgetMoveRepository
    from igab.repositories.category_repo import (
        BudgetAssignmentRepository,
        CategoryGroupRepository,
        CategoryRepository,
    )
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.budget_service import BudgetService

    return BudgetService(
        AccountRepository(session),
        CategoryRepository(session),
        CategoryGroupRepository(session),
        BudgetAssignmentRepository(session),
        TransactionRepository(session),
        move_repo=BudgetMoveRepository(session),
    )


async def _revision(session: AsyncSession) -> str:
    from igab.services.budget_snapshot import current_revision

    return await current_revision(session)


async def _import_export(session: AsyncSession, path: Path):
    """Load the export back through the same importer the app uses."""
    from igab.db.models import Budget, User
    from igab.integrations.ynab.importer import YNABImporter
    from igab.integrations.ynab.parser import YNABParser
    from igab.repositories.account_repo import AccountRepository
    from igab.repositories.attachment_repo import AttachmentRepository
    from igab.repositories.category_repo import (
        BudgetAssignmentRepository,
        CategoryGroupRepository,
        CategoryRepository,
    )
    from igab.repositories.payee_repo import PayeeRepository
    from igab.repositories.transaction_match_repo import TransactionMatchRepository
    from igab.repositories.transaction_repo import TransactionRepository
    from igab.services.account_type_service import ensure_account_types_seeded
    from igab.services.budget_provisioning import grant_owner
    from igab.services.transaction_service import TransactionService

    parsed = YNABParser().parse_zip(path)
    user = (await session.execute(select(User).limit(1))).scalars().one()
    budget = Budget(user_id=user.id, name="Imported Fixture", currency_code="USD")
    session.add(budget)
    await session.flush()
    grant_owner(session, budget.id, user.id)
    await ensure_account_types_seeded(session, budget.id)

    transaction_repo = TransactionRepository(session)
    account_repo = AccountRepository(session)
    category_repo = CategoryRepository(session)
    payee_repo = PayeeRepository(session)
    importer = YNABImporter(
        session=session,
        budget_id=budget.id,
        account_repo=account_repo,
        category_group_repo=CategoryGroupRepository(session),
        category_repo=category_repo,
        payee_repo=payee_repo,
        transaction_repo=transaction_repo,
        transaction_service=TransactionService(
            session,
            transaction_repo,
            account_repo,
            category_repo,
            payee_repo,
            attachment_repo=AttachmentRepository(session),
            match_repo=TransactionMatchRepository(session),
        ),
        assignment_repo=BudgetAssignmentRepository(session),
        # The real types travel in Accounts.csv, so nothing is guessed here.
        account_types=dict(parsed.account_types),
    )
    await importer.import_budget(parsed)
    await session.flush()
    return budget.id


async def _expected(session: AsyncSession, services, budget_id) -> dict:
    """What the file MEANT when it was written.

    Never edited to match new behaviour. If a genuine bug fix changes what an
    old file should produce, that is a deliberate diff with a reason in the
    commit message — and exactly the diff a reviewer needs to see.
    """
    from igab.repositories.category_repo import CategoryRepository

    named = await CategoryRepository(session).get_all_with_group_names(
        budget_id, include_hidden=True
    )
    names = {c.id: f"{g}: {c.name}" for c, g in named}

    months = {}
    for offset in range(-12, 1):
        month = date(
            ANCHOR.year + (ANCHOR.month - 1 + offset) // 12,
            (ANCHOR.month - 1 + offset) % 12 + 1,
            1,
        )
        summary = await services.get_budget_summary(budget_id, month)
        months[month.isoformat()] = {
            "to_be_assigned": str(summary.to_be_assigned),
            "total_overspent": str(summary.total_overspent),
            "categories": {
                names[b.category_id]: [str(b.assigned), str(b.activity), str(b.available)]
                for b in summary.category_balances
                if b.category_id in names
            },
        }
    return {"anchor": ANCHOR.isoformat(), "months": months}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new", action="store_true", help="mint a fresh dated directory")
    parser.add_argument("--version", help="the directory name, e.g. v1-2026-08")
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "FIXTURE_DATABASE_URL",
            "postgresql+asyncpg://igab:changeme@localhost:5432/igab_fixture_capture",
        ),
        help="a THROWAWAY database; its schema is created from the models",
    )
    args = parser.parse_args(argv[1:])

    if not args.new and not args.version:
        parser.error("pass --new, or --version <name>")
    version = args.version or default_version()

    asyncio.run(capture(version, args.database_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
