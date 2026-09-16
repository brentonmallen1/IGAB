"""The Savings report's three sections: Saved, On the way to savings, Sinking funds.

- **Saved** is kept-here Savings and Emergency fund envelopes plus off-budget
  accounts that count as savings. Moving money from one to the other moves
  nothing in Saved.
- **On the way to savings** is what sent-out envelopes still hold. It counts as
  saved when it leaves, so it is never added to Saved.
- **Sinking funds** are Long-term expense envelopes that are not savings — spoken
  for, never Saved.
- **On-budget accounts are never listed**: their money is already in the
  envelopes.

Names are the shared invented vocabulary; amounts are round enough to check on
paper. The clock is pinned mid-March, so the window for `months=3` is January to
March.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from igab.db.models import Account, BudgetMove, CategoryTarget, Transaction
from igab.domain.activity_class import ACTIVITY_CLASS, ActivityClass, apply_class_joins
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.txn_filters import SAVINGS_ACCOUNT
from igab.services.savings_report import savings_report
from tests.report_clock import report_today

from .factories import (
    create_account,
    create_budget,
    create_budget_assignment,
    create_category,
    create_category_group,
    create_transaction,
    create_transfer,
    create_user,
)

D = Decimal
TODAY = date(2026, 3, 15)
JAN, FEB, MAR = date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)


@pytest.fixture(autouse=True)
def _pinned_clock():
    with report_today(TODAY):
        yield


async def _world(db_session) -> dict:
    user = await create_user(db_session)
    budget = await create_budget(db_session, user)
    await seed_system_tags(db_session, budget.id)
    return {
        "budget": budget,
        "checking": await create_account(db_session, budget, "Checking"),
        "goals": await create_category_group(db_session, budget, "Goals"),
    }


async def _envelope(db_session, w, name: str, *keys: str, mode: str | None = None):
    category = await create_category(db_session, w["budget"], w["goals"], name)
    tags = TagRepository(db_session)
    ids = [(await tags.get_system_tag(w["budget"].id, k)).id for k in keys]
    await tags.set_category_tags(category.id, ids)
    category.savings_mode = mode
    await db_session.flush()
    return category


async def _hysa(db_session, w, name="Cascade Point HYSA", **kw):
    kw.setdefault("account_type", "savings")
    kw.setdefault("on_budget", False)
    kw.setdefault("counts_as_savings", True)
    return await create_account(db_session, w["budget"], name, **kw)


async def _report(db_session, w) -> dict:
    return await savings_report(db_session, w["budget"].id, months=3)


def _names(section: dict) -> list[str]:
    return [e["category_name"] for e in section["envelopes"]]


async def test_saved_counts_envelope_and_off_budget_account_without_double_count(db_session):
    """General Savings (kept here) is assigned 500 in February, then sends 300
    to Cascade Point HYSA in March. February: 500 in the envelope, 0 in the
    account. March: 200 and 300. Saved is 500 at both month ends."""
    w = await _world(db_session)
    kept = await _envelope(db_session, w, "General Savings", "savings", mode="kept_here")
    hysa = await _hysa(db_session, w)
    await create_budget_assignment(db_session, w["budget"], kept, FEB, "500")
    await create_transfer(
        db_session, w["budget"], w["checking"], hysa, "300", date(2026, 3, 5), category=kept
    )

    saved = (await _report(db_session, w))["saved"]

    assert _names(saved) == ["General Savings"]
    assert saved["envelopes"][0]["current_balance"] == D("200")
    assert [(a["name"], a["current_balance"]) for a in saved["accounts"]] == [
        ("Cascade Point HYSA", D("300"))
    ]
    assert saved["accounts"][0]["monthly_balances"] == [None, None, D("300")]
    assert (saved["envelopes_total"], saved["accounts_total"], saved["total"]) == (
        D("200"),
        D("300"),
        D("500"),
    )
    assert saved["monthly_totals"] == [D("0"), D("500"), D("500")]


async def test_an_on_budget_savings_account_is_never_added(db_session):
    """A savings-type account on budget that counts as savings: its 1,000 is
    already Ready to Assign or in envelopes, so the report lists nothing."""
    w = await _world(db_session)
    on_budget = await create_account(
        db_session,
        w["budget"],
        "Harborstone Savings",
        account_type="savings",
        on_budget=True,
        counts_as_savings=True,
    )
    await create_transaction(db_session, w["budget"], on_budget, "1000", FEB)

    saved = (await _report(db_session, w))["saved"]

    assert saved["accounts"] == []
    assert saved["total"] == D("0")


async def test_on_the_way_is_not_in_saved(db_session):
    """Investing (sent out) holds 400 until it leaves; General Savings (kept
    here) holds 250. Saved is 250, not 650."""
    w = await _world(db_session)
    sent = await _envelope(db_session, w, "Investing", "savings", mode="sent_out")
    kept = await _envelope(db_session, w, "General Savings", "savings", mode="kept_here")
    await create_budget_assignment(db_session, w["budget"], sent, MAR, "400")
    await create_budget_assignment(db_session, w["budget"], kept, MAR, "250")

    data = await _report(db_session, w)

    assert _names(data["on_the_way"]) == ["Investing"]
    assert data["on_the_way"]["total"] == D("400")
    assert _names(data["saved"]) == ["General Savings"]
    assert data["saved"]["total"] == D("250")


async def test_an_emergency_fund_envelope_is_saved_by_default(db_session):
    """Emergency fund with no stored mode is kept here: Saved. Set to sent out,
    the same envelope is On the way."""
    w = await _world(db_session)
    fund = await _envelope(db_session, w, "Emergency Fund", "emergency_fund")
    await create_budget_assignment(db_session, w["budget"], fund, JAN, "600")

    assert _names((await _report(db_session, w))["saved"]) == ["Emergency Fund"]

    fund.savings_mode = "sent_out"
    await db_session.flush()
    data = await _report(db_session, w)
    assert _names(data["saved"]) == []
    assert _names(data["on_the_way"]) == ["Emergency Fund"]


async def test_sinking_funds_are_never_in_saved(db_session):
    w = await _world(db_session)
    roof = await _envelope(db_session, w, "New Roof", "long_term_expense")
    await create_budget_assignment(db_session, w["budget"], roof, FEB, "900")

    data = await _report(db_session, w)

    assert _names(data["sinking_funds"]) == ["New Roof"]
    assert data["sinking_funds"]["total"] == D("900")
    assert data["saved"]["total"] == D("0")
    assert data["on_the_way"]["total"] == D("0")


async def test_a_savings_and_long_term_expense_category_is_savings_not_sinking(db_session):
    """No silent precedence at the tags, but one section per envelope: a
    savings category is not a sinking fund (`IS_SINKING_FUND`)."""
    w = await _world(db_session)
    both = await _envelope(
        db_session, w, "Vacation", "savings", "long_term_expense", mode="kept_here"
    )
    await create_budget_assignment(db_session, w["budget"], both, FEB, "300")

    data = await _report(db_session, w)

    assert _names(data["saved"]) == ["Vacation"]
    assert _names(data["sinking_funds"]) == []


async def test_a_savings_balance_target_serves_progress(db_session):
    """A 1,000 balance goal holding 600 is 60% of the way, and the Budget
    page's pill for it mid-month past the funding day is underfunded. A
    monthly funding target has a status and no progress."""
    w = await _world(db_session)
    fund = await _envelope(db_session, w, "Emergency Fund", "emergency_fund")
    roof = await _envelope(db_session, w, "New Roof", "long_term_expense")
    await create_budget_assignment(db_session, w["budget"], fund, FEB, "600")
    await create_budget_assignment(db_session, w["budget"], roof, MAR, "100")
    db_session.add_all(
        [
            CategoryTarget(
                category_id=fund.id, target_type="savings_balance", target_amount=D("1000")
            ),
            CategoryTarget(
                category_id=roof.id, target_type="monthly_funding", target_amount=D("100")
            ),
        ]
    )
    await db_session.flush()

    data = await _report(db_session, w)

    assert data["saved"]["envelopes"][0]["target"] == {
        "type": "savings_balance",
        "amount": D("1000"),
        "target_date": None,
        "status": "underfunded",
        "progress": D("0.6"),
    }
    roof_target = data["sinking_funds"]["envelopes"][0]["target"]
    assert (roof_target["status"], roof_target["progress"]) == ("funded", None)


async def test_an_overspent_envelope_counts_nothing_toward_its_section(db_session):
    """General Savings holds 100 and spends 250 in March: the row states the
    page's -150, and Saved counts 0 — Ready to Assign covered it."""
    w = await _world(db_session)
    kept = await _envelope(db_session, w, "General Savings", "savings", mode="kept_here")
    await create_budget_assignment(db_session, w["budget"], kept, FEB, "100")
    await create_transaction(
        db_session, w["budget"], w["checking"], "-250", date(2026, 3, 3), category=kept
    )

    saved = (await _report(db_session, w))["saved"]

    assert saved["envelopes"][0]["current_balance"] == D("-150")
    assert saved["total"] == D("0")
    assert saved["monthly_totals"] == [D("0"), D("100"), D("0")]


async def test_a_closed_account_that_held_nothing_is_not_a_row(db_session):
    w = await _world(db_session)
    closed = await _hysa(db_session, w, "Old Harborstone Reserve")
    closed.is_closed = True
    await db_session.flush()

    assert (await _report(db_session, w))["saved"]["accounts"] == []


async def test_drains_are_savings_envelopes_not_sinking_funds(db_session):
    w = await _world(db_session)
    kept = await _envelope(db_session, w, "General Savings", "savings", mode="kept_here")
    roof = await _envelope(db_session, w, "New Roof", "long_term_expense")
    for category in (kept, roof):
        await create_budget_assignment(db_session, w["budget"], category, FEB, "200")
        db_session.add(
            BudgetMove(
                budget_id=w["budget"].id,
                month=MAR,
                from_category_id=category.id,
                to_category_id=None,
                amount=D("50"),
            )
        )
    await db_session.flush()

    drains = (await _report(db_session, w))["drains"]

    assert drains["total"] == D("50")
    assert [m["from_name"] for m in drains["moves"]] == ["General Savings"]


# (name, account_type, on_budget, counts_as_savings)
ACCOUNT_SHAPES = [
    ("on-budget savings", "savings", True, True),
    ("off-budget savings", "savings", False, True),
    ("off-budget savings, not counted", "savings", False, False),
    ("off-budget investment", "investment", False, True),
    ("off-budget other asset", "other_asset", False, False),
    ("off-budget loan", "loan", False, True),
]


@pytest.mark.parametrize(
    ("_case", "account_type", "on_budget", "counts"),
    ACCOUNT_SHAPES,
    ids=[s[0] for s in ACCOUNT_SHAPES],
)
async def test_the_saved_account_list_agrees_with_rule_3(
    db_session, _case, account_type, on_budget, counts
):
    """An account is listed under Saved exactly when a transfer into it is
    SAVINGS by the classifier's rule 3 — so the report never lists an account
    the savings rate calls spending, nor leaves out one it calls saving."""
    w = await _world(db_session)
    account = await create_account(
        db_session,
        w["budget"],
        "Destination",
        account_type=account_type,
        on_budget=on_budget,
        counts_as_savings=counts,
    )
    out, _ = await create_transfer(db_session, w["budget"], w["checking"], account, "100", FEB)

    klass = (
        await db_session.execute(
            apply_class_joins(
                select(Transaction.id, ACTIVITY_CLASS).where(Transaction.id == out.id)
            )
        )
    ).one()[1]
    listed = (
        await db_session.execute(select(SAVINGS_ACCOUNT).where(Account.id == account.id))
    ).scalar_one()

    assert (klass == ActivityClass.SAVINGS) == listed
    assert [a["name"] for a in (await _report(db_session, w))["saved"]["accounts"]] == (
        ["Destination"] if listed else []
    )


async def test_the_endpoint_serves_every_section(db_session, api_client):
    budget = await create_budget(db_session, api_client.test_user)
    await seed_system_tags(db_session, budget.id)
    w = {
        "budget": budget,
        "checking": await create_account(db_session, budget, "Checking"),
        "goals": await create_category_group(db_session, budget, "Goals"),
    }
    fund = await _envelope(db_session, w, "Emergency Fund", "emergency_fund")
    await create_budget_assignment(db_session, budget, fund, FEB, "600")
    await _hysa(db_session, w, "Harborstone Reserve")
    await db_session.commit()

    resp = await api_client.get(f"/api/v1/{budget.id}/reports/savings", params={"months": 3})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"saved", "on_the_way", "sinking_funds", "months", "drains", "unrecovered"}
    assert [e["category_name"] for e in body["saved"]["envelopes"]] == ["Emergency Fund"]
    [reserve] = body["saved"]["accounts"]
    assert (reserve["name"], reserve["monthly_balances"]) == ("Harborstone Reserve", [None] * 3)
