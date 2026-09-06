"""Storage for the import mapping step's memory.

Plain, like SettingsRepository: there is no id-keyed access and no soft
delete here, so BaseRepository would only add surface. The rule this data
feeds lives in `domain.import_mapping`; this file does nothing but read and
write it.
"""

import uuid
from collections.abc import Mapping
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import ImportAccountMapping, new_uuid
from igab.domain.import_mapping import RememberedChoice, account_key


class _Choice(Protocol):
    """What `remember` needs of a submitted choice.

    Structural rather than importing YNABAccountTypeChoice: that model lives
    in the router, and a repository importing from `api/` is a cycle waiting
    to be written.
    """

    account_type: str
    on_budget: bool
    skip: bool
    close: bool


class ImportMappingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_user(self, user_id: uuid.UUID) -> dict[str, RememberedChoice]:
        """`account_key` → choice, so no caller has to re-derive the key."""
        result = await self.session.execute(
            select(ImportAccountMapping).where(ImportAccountMapping.user_id == user_id)
        )
        return {
            row.account_key: RememberedChoice(
                account_type=row.account_type,
                on_budget=row.on_budget,
                skip=row.skip,
                close=row.close,
            )
            for row in result.scalars().all()
        }

    async def remember(self, user_id: uuid.UUID, choices: Mapping[str, _Choice]) -> int:
        """Upsert one row per submitted account. Returns how many were written.

        Accumulated into a dict keyed by `account_key` before the insert, not
        because a register realistically carries both "Checking" and
        "checking", but because if it did, Postgres would raise "ON CONFLICT
        DO UPDATE command cannot affect row a second time" — two VALUES rows
        colliding on one conflict key — and the import would fail at the very
        end, after everything else had succeeded.
        """
        rows: dict[str, dict[str, Any]] = {}
        for name, choice in choices.items():
            key = account_key(name)
            rows[key] = {
                "id": new_uuid(),
                "user_id": user_id,
                "account_key": key,
                "account_name": name.strip(),
                "account_type": choice.account_type,
                "on_budget": choice.on_budget,
                "skip": choice.skip,
                "close": choice.close and not choice.skip,
            }
        if not rows:
            return 0
        stmt = pg_insert(ImportAccountMapping).values(list(rows.values()))
        await self.session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_import_mapping_user_account",
                set_={
                    "account_name": stmt.excluded.account_name,
                    "account_type": stmt.excluded.account_type,
                    "on_budget": stmt.excluded.on_budget,
                    "skip": stmt.excluded.skip,
                    "close": stmt.excluded.close,
                    # Set explicitly: the model's `onupdate` is a hook on
                    # UPDATE constructs and does not fire for ON CONFLICT.
                    "updated_at": func.now(),
                },
            )
        )
        await self.session.flush()
        return len(rows)

    async def forget_all(self, user_id: uuid.UUID) -> int:
        """Drop every remembered choice for one user, returning the count."""
        result = await self.session.execute(
            delete(ImportAccountMapping).where(ImportAccountMapping.user_id == user_id)
        )
        await self.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)
