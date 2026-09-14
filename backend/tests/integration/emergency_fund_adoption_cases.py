"""The emergency-fund adoption cases, stated once for both copies of the steps.

Migration `e52d44b73edb` converts every budget's old emergency-fund bindings;
`services/emergency_fund_adoption.adopt` converts one restored snapshot's the
same way. The two are separate copies on purpose (a migration is frozen), so
both suites build these rows and assert these outcomes: the migration test in a
scratch database upgraded through the real chain, the restore test through a
real snapshot. A difference between the copies fails one of them.

Sync and Core-only, so the scratch database (psycopg2, no ORM session) and the
async test session (`AsyncSession.run_sync`) can both run them. The schema at
the revision before adoption is the models' schema — the migration adds no
column — so `Base.metadata` tables are safe to insert through.

Names are the repo's invented vocabulary.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, insert, select

from igab.db.models import Base

PRE_ADOPTION_REVISION = "4d5612e7c044"


def _t(name: str):
    return Base.metadata.tables[name]


def _account_type(
    conn: Connection, budget_id: uuid.UUID, key: str, classification: str
) -> uuid.UUID:
    types = _t("account_types")
    found = conn.execute(
        select(types.c.id).where(types.c.budget_id == budget_id, types.c.key == key)
    ).scalar_one_or_none()
    if found is not None:
        return found
    return conn.execute(
        insert(types)
        .values(
            budget_id=budget_id,
            key=key,
            label=key,
            classification=classification,
            default_on_budget=classification != "liability",
            default_counts_as_savings=True,
            is_system=True,
        )
        .returning(types.c.id)
    ).scalar_one()


def _category(conn: Connection, budget_id: uuid.UUID, group_id: uuid.UUID, name: str) -> uuid.UUID:
    return conn.execute(
        insert(_t("categories"))
        .values(budget_id=budget_id, category_group_id=group_id, name=name)
        .returning(_t("categories").c.id)
    ).scalar_one()


def _tag(conn: Connection, budget_id: uuid.UUID, name: str, system_key: str | None) -> uuid.UUID:
    return conn.execute(
        insert(_t("tags"))
        .values(budget_id=budget_id, name=name, system_key=system_key)
        .returning(_t("tags").c.id)
    ).scalar_one()


def _account(
    conn: Connection,
    budget_id: uuid.UUID,
    name: str,
    *,
    key: str,
    classification: str = "asset",
    on_budget: bool,
    counts_as_savings: bool,
) -> uuid.UUID:
    return conn.execute(
        insert(_t("accounts"))
        .values(
            budget_id=budget_id,
            name=name,
            account_type_id=_account_type(conn, budget_id, key, classification),
            account_type=key,
            classification=classification,
            on_budget=on_budget,
            counts_as_savings=counts_as_savings,
        )
        .returning(_t("accounts").c.id)
    ).scalar_one()


def _bind(conn: Connection, budget_id: uuid.UUID, mode: str, **values) -> None:
    conn.execute(
        insert(_t("guide_bindings")).values(
            budget_id=budget_id, concept_key="emergency_fund", mode=mode, **values
        )
    )


def insert_budget(conn: Connection, name: str) -> uuid.UUID:
    """A user and a budget, for the scratch database that has neither."""
    user_id = conn.execute(
        insert(_t("users"))
        .values(email=f"{uuid.uuid4().hex[:8]}@example.test", password_hash="x" * 60)
        .returning(_t("users").c.id)
    ).scalar_one()
    return conn.execute(
        insert(_t("budgets")).values(user_id=user_id, name=name).returning(_t("budgets").c.id)
    ).scalar_one()


@dataclass(frozen=True)
class ChosenBudget:
    budget_id: uuid.UUID
    bound: uuid.UUID
    bound_savings: uuid.UUID
    adopted: uuid.UUID
    user_tag: uuid.UUID
    hysa: uuid.UUID
    checking: uuid.UUID
    car: uuid.UUID


def build_chosen(conn: Connection, budget_id: uuid.UUID) -> ChosenBudget:
    """A budget that told the old Guide what its emergency fund was.

    - House Cushion: bound, untagged → tagged, mode left alone.
    - Rainy Day Savings: bound and tagged Savings → tagged, stamped sent out.
    - Buffer: NOT bound, tagged Savings and a user tag named "Emergency Fund"
      that seeding adopts → stamped sent out.
    - Cascade Point HYSA: bound off-budget savings → flagged.
    - Harborstone Checking: bound on budget → dropped, on_budget.
    - Second Car: bound off-budget, not savings → dropped, not_savings.
    - An external row, which stays.
    """
    group = conn.execute(
        insert(_t("category_groups"))
        .values(budget_id=budget_id, name="Goals")
        .returning(_t("category_groups").c.id)
    ).scalar_one()
    savings_tag = _tag(conn, budget_id, "Savings", "savings")
    user_tag = _tag(conn, budget_id, "Emergency Fund", None)
    bound = _category(conn, budget_id, group, "House Cushion")
    bound_savings = _category(conn, budget_id, group, "Rainy Day Savings")
    adopted = _category(conn, budget_id, group, "Buffer")
    memberships = _t("category_tags")
    conn.execute(
        insert(memberships),
        [
            {"category_id": bound_savings, "tag_id": savings_tag},
            {"category_id": adopted, "tag_id": savings_tag},
            {"category_id": adopted, "tag_id": user_tag},
        ],
    )
    hysa = _account(
        conn,
        budget_id,
        "Cascade Point HYSA",
        key="savings",
        on_budget=False,
        counts_as_savings=True,
    )
    checking = _account(
        conn,
        budget_id,
        "Harborstone Checking",
        key="checking",
        on_budget=True,
        counts_as_savings=True,
    )
    car = _account(
        conn, budget_id, "Second Car", key="other_asset", on_budget=False, counts_as_savings=False
    )
    for category in (bound, bound_savings):
        _bind(conn, budget_id, "manual", entity_type="category", entity_id=category)
    for account in (hysa, checking, car):
        _bind(conn, budget_id, "manual", entity_type="account", entity_id=account)
    _bind(conn, budget_id, "external", amount=1000, note="credit union")
    return ChosenBudget(budget_id, bound, bound_savings, adopted, user_tag, hysa, checking, car)


def build_guess_only(conn: Connection, budget_id: uuid.UUID) -> uuid.UUID:
    """No binding at all, and a category the old guess would have read."""
    group = conn.execute(
        insert(_t("category_groups"))
        .values(budget_id=budget_id, name="Goals")
        .returning(_t("category_groups").c.id)
    ).scalar_one()
    return _category(conn, budget_id, group, "Rainy Day")


def build_dismissed(conn: Connection, budget_id: uuid.UUID) -> None:
    """The concept dismissed, beside a name the guess would have read."""
    build_guess_only(conn, budget_id)
    _bind(conn, budget_id, "dismissed", note="not for me")


def _fund_tag(conn: Connection, budget_id: uuid.UUID):
    tags = _t("tags")
    return conn.execute(
        select(tags).where(
            tags.c.budget_id == budget_id,
            tags.c.system_key == "emergency_fund",
            tags.c.is_deleted.is_(False),
        )
    ).one()


def _members(conn: Connection, tag_id: uuid.UUID) -> set[uuid.UUID]:
    memberships = _t("category_tags")
    return set(
        conn.execute(
            select(memberships.c.category_id).where(memberships.c.tag_id == tag_id)
        ).scalars()
    )


def _notices(conn: Connection, budget_id: uuid.UUID) -> dict[str, dict]:
    state = _t("guide_state")
    return {
        row.key: row.value
        for row in conn.execute(
            select(state.c.key, state.c.value).where(
                state.c.budget_id == budget_id, state.c.key.like("notice:emergency_fund%")
            )
        )
    }


def _modes(conn: Connection, budget_id: uuid.UUID) -> list[str]:
    bindings = _t("guide_bindings")
    return sorted(
        conn.execute(
            select(bindings.c.mode).where(
                bindings.c.budget_id == budget_id, bindings.c.concept_key == "emergency_fund"
            )
        ).scalars()
    )


def assert_chosen_adopted(conn: Connection, case: ChosenBudget) -> None:
    tag = _fund_tag(conn, case.budget_id)
    assert tag.id == case.user_tag, "the same-named user tag is adopted, not duplicated"
    assert tag.color_slot == "green"
    assert _members(conn, tag.id) == {case.bound, case.bound_savings, case.adopted}

    categories = _t("categories")
    modes = dict(
        conn.execute(
            select(categories.c.id, categories.c.savings_mode).where(
                categories.c.budget_id == case.budget_id
            )
        ).all()
    )
    assert modes[case.bound] is None, "not a Savings category: the new default is the choice"
    assert modes[case.bound_savings] == "sent_out"
    assert modes[case.adopted] == "sent_out"

    accounts = _t("accounts")
    flags = dict(
        conn.execute(
            select(accounts.c.id, accounts.c.counts_toward_emergency_fund).where(
                accounts.c.budget_id == case.budget_id
            )
        ).all()
    )
    assert (flags[case.hysa], flags[case.checking], flags[case.car]) == (True, False, False)

    assert _modes(conn, case.budget_id) == ["external"]
    assert _notices(conn, case.budget_id) == {
        "notice:emergency_fund_chosen": {
            "tagged_categories": ["House Cushion", "Rainy Day Savings"],
            "flagged_accounts": ["Cascade Point HYSA"],
            "dropped_accounts": [
                {"name": "Harborstone Checking", "reason": "on_budget"},
                {"name": "Second Car", "reason": "not_savings"},
            ],
        }
    }


def assert_guess_only_adopted(conn: Connection, budget_id: uuid.UUID) -> None:
    tag = _fund_tag(conn, budget_id)
    assert _members(conn, tag.id) == set(), "nothing is guessed"
    assert _modes(conn, budget_id) == []
    assert _notices(conn, budget_id) == {"notice:emergency_fund_not_guessed": {}}


def assert_dismissed_adopted(conn: Connection, budget_id: uuid.UUID) -> None:
    tag = _fund_tag(conn, budget_id)
    assert _members(conn, tag.id) == set()
    assert _modes(conn, budget_id) == ["dismissed"]
    assert _notices(conn, budget_id) == {}
