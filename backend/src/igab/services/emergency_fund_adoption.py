"""Turning a budget's old emergency-fund answer into what the fund reads now.

The emergency fund used to be a Guide binding — `manual` rows pointing at
categories and accounts — or, with no binding, a guess from names and account
types. It is now the Emergency fund tag, the account flag, and the declared
amount (`services/emergency_fund.py`). Migration `e52d44b73edb` converts every
budget once; this converts ONE budget the same way, for a budget snapshot taken
before that migration and restored after it (`services/budget_snapshot.py`),
whose rows arrive still speaking the old vocabulary.

**Two copies, on purpose, and pinned.** A migration must replay identically
forever, so it inlines a frozen copy of these statements rather than importing
this module; this module is the live copy. `test_restoring_a_pre_adoption_
snapshot_adopts_like_the_migration` runs both over the same rows and compares
what they left. Change one and that test says so.

In order, for the budget:

1. Seed or adopt the `emergency_fund` system tag (`seed_system_tags`).
2. Every `manual` category binding on a live category of this budget → the
   Emergency fund tag.
3. Every category tagged both Savings and Emergency fund with no stored mode →
   `sent_out`. Savings meant sent out, and the new tag's default is kept here,
   so without this a category the household had tagged Savings, and a user tag
   named "Emergency Fund" that seeding adopts, would change the savings rate.
4. Every `manual` account binding on a live off-budget, non-liability account
   that counts as savings → `counts_toward_emergency_fund`.
5. Every other live account binding is dropped, with its reason: `on_budget`
   (its envelopes say what its money is for) or `not_savings`.
6. The `manual` rows go. External, dismissed and answer rows stay.
7. A budget that had manual rows gets `notice:emergency_fund_chosen`, naming
   what was tagged, flagged and dropped.
8. A budget with no manual rows that was not dismissed, where the old guess
   would have found something, gets `notice:emergency_fund_not_guessed` —
   nothing is tagged for it.
"""

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from igab.repositories.tag_repo import seed_system_tags

#: The migration that ran these steps on every budget. A snapshot exported at an
#: earlier revision is adopted on restore.
ADOPTION_REVISION = "e52d44b73edb"

CHOSEN_NOTICE = "notice:emergency_fund_chosen"
NOT_GUESSED_NOTICE = "notice:emergency_fund_not_guessed"

#: The old guess's name rule (`GuideDetection.EMERGENCY_NAME`, deleted), as a
#: Postgres case-insensitive regex. Frozen: it answers "would the old app have
#: guessed", which is a question about the old app.
OLD_GUESS_NAME = "emergency|rainy.?day|buffer"


async def adopt(session: AsyncSession, budget_id: uuid.UUID) -> None:
    """Convert one budget's emergency-fund bindings. Safe to call on a budget
    that has none: it seeds the tag and, at most, writes the not-guessed
    notice — which is why a snapshot of the current schema is never passed
    here (`budget_snapshot._load`)."""
    params = {"budget_id": budget_id}

    async def rows(sql: str) -> list[Any]:
        return list((await session.execute(text(sql), params)).all())

    async def run(sql: str, extra: dict[str, Any] | None = None) -> None:
        await session.execute(text(sql), {**params, **(extra or {})})

    # 1.
    await seed_system_tags(session, budget_id)

    manual = await rows(
        "SELECT entity_type, entity_id FROM guide_bindings "
        "WHERE budget_id = :budget_id AND concept_key = 'emergency_fund' AND mode = 'manual'"
    )
    dismissed = await rows(
        "SELECT 1 FROM guide_bindings "
        "WHERE budget_id = :budget_id AND concept_key = 'emergency_fund' AND mode = 'dismissed'"
    )

    tagged: list[Any] = []
    if manual:
        # 2.
        tagged = await rows(
            """
            SELECT c.id, c.name FROM guide_bindings g
            JOIN categories c ON c.id = g.entity_id AND c.budget_id = g.budget_id
            WHERE g.budget_id = :budget_id AND g.concept_key = 'emergency_fund'
              AND g.mode = 'manual' AND g.entity_type = 'category' AND NOT c.is_deleted
            ORDER BY c.name, c.id
            """
        )
        await run(
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

    # 3. Every budget, not only those with bindings: seeding may have adopted
    # a user tag named "Emergency Fund" on a category already tagged Savings.
    await run(
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
        accounts = await rows(
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
                await run(
                    "UPDATE accounts SET counts_toward_emergency_fund = true "
                    "WHERE id = :account_id",
                    {"account_id": account.id},
                )
        # 6.
        await run(
            "DELETE FROM guide_bindings "
            "WHERE budget_id = :budget_id AND concept_key = 'emergency_fund' AND mode = 'manual'"
        )
        # 7.
        await _notice(
            session,
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
        guessed = await rows(
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
            await _notice(session, budget_id, NOT_GUESSED_NOTICE, {})
    await session.flush()


async def _notice(
    session: AsyncSession, budget_id: uuid.UUID, key: str, payload: dict[str, Any]
) -> None:
    from igab.guide.repo import GuideRepository

    await GuideRepository(session).set_state(budget_id, key, payload)
