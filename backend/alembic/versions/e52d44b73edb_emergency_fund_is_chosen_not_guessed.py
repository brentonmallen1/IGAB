"""the emergency fund is chosen, not guessed

The emergency fund was a Guide binding: `manual` rows in `guide_bindings`
pointing at categories and accounts, or — with none — a guess from category
names and savings-type accounts. It is now three budget facts every surface
reads (`services/emergency_fund.py`): the Emergency fund system tag on
envelopes, `accounts.counts_toward_emergency_fund` on off-budget savings
accounts, and the declared amount kept elsewhere (the `external` rows, which
stay). The Guide concept binds to nothing now, so this converts every budget's
manual rows and removes them.

For every budget, in order:

1. Seed or adopt the `emergency_fund` system tag, as `seed_system_tags` does:
   a live same-named tag with no system key (case-insensitive) is adopted,
   otherwise one is inserted.
2. Manual category bindings on a live category of the budget → the tag.
3. Categories tagged both Savings and Emergency fund with no stored
   `savings_mode` → `sent_out`. The new tag defaults to kept here, and Savings
   always meant sent out: without this a bound category that was tagged
   Savings, or a Savings category carrying an adopted "Emergency Fund" user
   tag, would change the savings rate on upgrade.
4. Manual account bindings on a live off-budget, non-liability account that
   counts as savings → `counts_toward_emergency_fund = true`.
5. Every other live bound account is dropped with a reason — `on_budget`
   (its envelopes already say what its money is for) or `not_savings`.
6. The manual rows are deleted. External, dismissed and answer rows stay.
7. A budget that had manual rows gets the Tags notice
   `notice:emergency_fund_chosen` {tagged_categories, flagged_accounts,
   dropped_accounts: [{name, reason}]}.
8. A budget with no manual rows that had not dismissed the concept is tagged
   nothing; where the old guess would have found something (a live category
   named like /emergency|rainy.?day|buffer/i, or a live account of type
   `savings`) it gets `notice:emergency_fund_not_guessed` {}.

Frozen SQL: no model imports, and the old guess's regex inlined (precedent
e3f1a8c5d920), so this replays identically forever. The live copy of the same
steps is `services/emergency_fund_adoption.py`, which a restore runs on a
snapshot taken before this revision; a test runs both over the same rows.

Downgrade removes the two notices only. The seeded tag, the memberships and
account flags written here and the deleted manual rows are not reversed: the
old code reads an unknown system tag as a plain tag, and the rows it would need
back are gone. Undoing an old binding edit after this revision raises the undo
conflict rather than restoring rows nothing reads.

Revision ID: e52d44b73edb
Revises: 4d5612e7c044
Create Date: 2026-09-14
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e52d44b73edb"
down_revision: str | Sequence[str] | None = "4d5612e7c044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHOSEN_NOTICE = "notice:emergency_fund_chosen"
NOT_GUESSED_NOTICE = "notice:emergency_fund_not_guessed"
#: Frozen copy of the deleted `GuideDetection.EMERGENCY_NAME`.
OLD_GUESS_NAME = "emergency|rainy.?day|buffer"


def _notice(conn, budget_id, key: str, payload: dict) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO guide_state (id, budget_id, key, value, updated_at)
            VALUES (gen_random_uuid(), :budget_id, :key, CAST(:value AS jsonb), now())
            ON CONFLICT (budget_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """
        ),
        {"budget_id": budget_id, "key": key, "value": json.dumps(payload)},
    )


def _adopt(conn, budget_id) -> None:
    params = {"budget_id": budget_id}

    def rows(sql: str) -> list:
        return list(conn.execute(sa.text(sql), params).all())

    def run(sql: str, extra: dict | None = None) -> None:
        conn.execute(sa.text(sql), {**params, **(extra or {})})

    # 1. Seed or adopt.
    has_tag = rows(
        "SELECT 1 FROM tags WHERE budget_id = :budget_id "
        "AND system_key = 'emergency_fund' AND NOT is_deleted"
    )
    if not has_tag:
        claimed = rows(
            "SELECT id FROM tags WHERE budget_id = :budget_id "
            "AND lower(name) = 'emergency fund' AND system_key IS NULL AND NOT is_deleted"
        )
        if claimed:
            run(
                "UPDATE tags SET system_key = 'emergency_fund', color_slot = 'green', "
                "updated_at = now() WHERE id = :tag_id",
                {"tag_id": claimed[0].id},
            )
        else:
            run(
                "INSERT INTO tags (id, budget_id, name, system_key, color_slot, is_deleted, "
                "created_at, updated_at) VALUES (gen_random_uuid(), :budget_id, "
                "'Emergency fund', 'emergency_fund', 'green', false, now(), now())"
            )

    manual = rows(
        "SELECT entity_type, entity_id FROM guide_bindings "
        "WHERE budget_id = :budget_id AND concept_key = 'emergency_fund' AND mode = 'manual'"
    )
    dismissed = rows(
        "SELECT 1 FROM guide_bindings "
        "WHERE budget_id = :budget_id AND concept_key = 'emergency_fund' AND mode = 'dismissed'"
    )

    tagged: list = []
    if manual:
        # 2.
        tagged = rows(
            """
            SELECT c.id, c.name FROM guide_bindings g
            JOIN categories c ON c.id = g.entity_id AND c.budget_id = g.budget_id
            WHERE g.budget_id = :budget_id AND g.concept_key = 'emergency_fund'
              AND g.mode = 'manual' AND g.entity_type = 'category' AND NOT c.is_deleted
            ORDER BY c.name, c.id
            """
        )
        run(
            """
            INSERT INTO category_tags (category_id, tag_id)
            SELECT c.id, t.id FROM guide_bindings g
            JOIN categories c ON c.id = g.entity_id AND c.budget_id = g.budget_id
            JOIN tags t ON t.budget_id = g.budget_id AND t.system_key = 'emergency_fund'
                       AND NOT t.is_deleted
            WHERE g.budget_id = :budget_id AND g.concept_key = 'emergency_fund'
              AND g.mode = 'manual' AND g.entity_type = 'category' AND NOT c.is_deleted
            ON CONFLICT DO NOTHING
            """
        )

    # 3.
    run(
        """
        UPDATE categories c SET savings_mode = 'sent_out'
        WHERE c.budget_id = :budget_id AND c.savings_mode IS NULL
          AND EXISTS (SELECT 1 FROM category_tags ct JOIN tags t ON t.id = ct.tag_id
                      WHERE ct.category_id = c.id AND t.system_key = 'savings'
                        AND NOT t.is_deleted)
          AND EXISTS (SELECT 1 FROM category_tags ct JOIN tags t ON t.id = ct.tag_id
                      WHERE ct.category_id = c.id AND t.system_key = 'emergency_fund'
                        AND NOT t.is_deleted)
        """
    )

    if manual:
        accounts = rows(
            """
            SELECT a.id, a.name, a.on_budget, a.classification, a.counts_as_savings
            FROM guide_bindings g
            JOIN accounts a ON a.id = g.entity_id AND a.budget_id = g.budget_id
            WHERE g.budget_id = :budget_id AND g.concept_key = 'emergency_fund'
              AND g.mode = 'manual' AND g.entity_type = 'account' AND NOT a.is_deleted
            ORDER BY a.name, a.id
            """
        )
        flagged: list[str] = []
        dropped: list[dict[str, str]] = []
        for account in accounts:
            if account.on_budget:
                dropped.append({"name": account.name, "reason": "on_budget"})
            elif account.classification == "liability" or not account.counts_as_savings:
                dropped.append({"name": account.name, "reason": "not_savings"})
            else:
                flagged.append(account.name)
                # 4.
                run(
                    "UPDATE accounts SET counts_toward_emergency_fund = true "
                    "WHERE id = :account_id",
                    {"account_id": account.id},
                )
        # 6.
        run(
            "DELETE FROM guide_bindings "
            "WHERE budget_id = :budget_id AND concept_key = 'emergency_fund' AND mode = 'manual'"
        )
        # 7.
        _notice(
            conn,
            budget_id,
            CHOSEN_NOTICE,
            {
                "tagged_categories": [r.name for r in tagged],
                "flagged_accounts": flagged,
                "dropped_accounts": dropped,
            },
        )
    elif not dismissed:
        # 8.
        guessed = rows(
            f"""
            SELECT 1 WHERE EXISTS (
                SELECT 1 FROM categories c WHERE c.budget_id = :budget_id
                  AND NOT c.is_deleted AND c.name ~* '{OLD_GUESS_NAME}'
            ) OR EXISTS (
                SELECT 1 FROM accounts a WHERE a.budget_id = :budget_id
                  AND NOT a.is_deleted AND a.account_type = 'savings'
            )
            """
        )
        if guessed:
            _notice(conn, budget_id, NOT_GUESSED_NOTICE, {})


def upgrade() -> None:
    conn = op.get_bind()
    for (budget_id,) in conn.execute(sa.text("SELECT id FROM budgets ORDER BY id")).all():
        _adopt(conn, budget_id)


def downgrade() -> None:
    op.execute(f"DELETE FROM guide_state WHERE key IN ('{CHOSEN_NOTICE}', '{NOT_GUESSED_NOTICE}')")
