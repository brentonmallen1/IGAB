"""Assets and their dated value points.

The one writer of the (`manual_value`, `value_as_of`) pair: every mutation of
the snapshot series re-derives both from the newest surviving point, so the
pair can never drift apart or outlive the row it came from. Writing either
column anywhere else is how the freshest point on the net-worth chart becomes
the one with no provenance (`Liability.manual_balance`'s standing defect).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select, update

from igab.db.models import Asset, AssetValueSnapshot, Liability
from igab.repositories.base import BaseRepository


class AssetRepository(BaseRepository[Asset]):
    model = Asset

    async def get_all(self, budget_id: uuid.UUID) -> list[Asset]:
        result = await self.session.execute(
            select(Asset)
            .where(Asset.budget_id == budget_id, Asset.is_deleted == False)  # noqa: E712
            .order_by(Asset.name)
        )
        return list(result.scalars().all())

    async def get_values(self, asset_id: uuid.UUID) -> list[AssetValueSnapshot]:
        """Newest first — the order the value register reads in."""
        result = await self.session.execute(
            select(AssetValueSnapshot)
            .where(AssetValueSnapshot.asset_id == asset_id)
            .order_by(AssetValueSnapshot.date.desc())
        )
        return list(result.scalars().all())

    async def upsert_value(
        self,
        asset: Asset,
        value_date: date,
        value: Decimal,
        source: str = "manual",
    ) -> AssetValueSnapshot:
        """One point per day: a second entry for the same date replaces it.
        Mirrors LiabilityRepository.upsert_snapshot, then re-derives the
        denormalised pair."""
        result = await self.session.execute(
            select(AssetValueSnapshot).where(
                AssetValueSnapshot.asset_id == asset.id,
                AssetValueSnapshot.date == value_date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.value = value
            existing.source = source
            snapshot = existing
        else:
            snapshot = AssetValueSnapshot(
                asset_id=asset.id, date=value_date, value=value, source=source
            )
            self.session.add(snapshot)
        await self.session.flush()
        await self._rederive(asset)
        return snapshot

    async def update_value(
        self, asset: Asset, snapshot_id: uuid.UUID, value: Decimal
    ) -> AssetValueSnapshot | None:
        """Correct one point's figure. The date is identity here (one point
        per day); moving a point is a delete plus a new entry."""
        snapshot = await self.session.get(AssetValueSnapshot, snapshot_id)
        if snapshot is None or snapshot.asset_id != asset.id:
            return None
        snapshot.value = value
        await self.session.flush()
        await self._rederive(asset)
        return snapshot

    async def delete_value(self, asset: Asset, snapshot_id: uuid.UUID) -> bool:
        snapshot = await self.session.get(AssetValueSnapshot, snapshot_id)
        if snapshot is None or snapshot.asset_id != asset.id:
            return False
        await self.session.delete(snapshot)
        await self.session.flush()
        await self._rederive(asset)
        return True

    async def _rederive(self, asset: Asset) -> None:
        """(`manual_value`, `value_as_of`) = the newest surviving point, as a
        pair — deleting the newest point must fall back to the one before it,
        never strand the columns pointing at a row that no longer exists."""
        result = await self.session.execute(
            select(AssetValueSnapshot)
            .where(AssetValueSnapshot.asset_id == asset.id)
            .order_by(AssetValueSnapshot.date.desc())
            .limit(1)
        )
        newest = result.scalars().first()
        asset.manual_value = newest.value if newest else None
        asset.value_as_of = newest.date if newest else None
        await self.session.flush()

    async def retire(self, asset: Asset) -> None:
        """Soft-delete, and unlink every liability pointing here ourselves:
        the FK's ondelete=SET NULL only fires on a real DELETE, which a soft
        delete never issues — the same duty AccountRepository.soft_delete
        carries for Category.linked_account_id. Named apart from the base
        class's id-keyed soft_delete because the unlink is not optional."""
        asset.is_deleted = True
        await self.session.execute(
            update(Liability)
            .where(Liability.linked_asset_id == asset.id)
            .values(linked_asset_id=None)
        )
        await self.session.flush()
