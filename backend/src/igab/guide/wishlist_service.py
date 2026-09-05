"""The wishlist: wishes, projects, and what the budget says about them.

Orchestration only. The rules are in `guide/wishlist.py` (pure) and the
money is the budget's: an envelope's balance comes from
`BudgetService.get_category_balance`, its pace from `TargetService`, and a
wish's own envelope is an ordinary category with a savings goal the budget
page owns from then on. The `wishlist` tag is derived from the wish→envelope
link here and nowhere else.
"""

import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryGroup, WishlistItem, WishlistProject
from igab.domain.dates import month_start
from igab.domain.drains import drains_total, shape_drains
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.domain.money import quantize_cents
from igab.domain.ordering import renumber
from igab.guide.detection import budget_service_from
from igab.guide.repo import GuideRepository
from igab.guide.service import DEFAULT_PREFS, PREFS_KEY
from igab.guide.wishlist import (
    DEFAULT_COOLING_DAYS,
    DEFAULT_REVIEW_DAYS,
    PRIORITY_LIMIT,
    STILL_WANTED_MONTHS,
    Funding,
    ProjectInput,
    Reach,
    WishInput,
    cooling_until_for,
    drain_impact,
    effective_category,
    project_summary,
    reach_for,
    review_due,
    still_wanted,
    trailing_average,
)
from igab.repositories.budget_move_repo import BudgetMoveRepository
from igab.repositories.category_repo import (
    BudgetAssignmentRepository,
    CategoryGroupRepository,
    CategoryRepository,
)
from igab.repositories.tag_repo import TagRepository, seed_system_tags
from igab.repositories.target_repo import TargetRepository
from igab.services.budget_service import BudgetService
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.target_service import TargetService

SETTINGS_KEY = "wishlist"
DEFAULT_SETTINGS: dict[str, int] = {
    "cooling_days": DEFAULT_COOLING_DAYS,
    "review_after_days": DEFAULT_REVIEW_DAYS,
}
STATUSES = ("open", "done", "dropped")


class WishlistService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        budget_service: BudgetService | None = None,
        target_service: TargetService | None = None,
    ) -> None:
        self.session = session
        self.budget = budget_service or budget_service_from(session)
        self.targets = target_service or TargetService(TargetRepository(session))
        self.categories = CategoryRepository(session)
        self.groups = CategoryGroupRepository(session)
        self.tags = TagRepository(session)
        self.assignments = BudgetAssignmentRepository(session)
        self.moves = BudgetMoveRepository(session)
        self.guide = GuideRepository(session)
        # Every mutation below records — the global undo is LIFO over the
        # change log, and this domain being invisible to it meant ⌘Z after a
        # wish delete silently reverted something older and unrelated.
        self.changes = ChangeRecorder(session)

    # ── switches and settings ────────────────────────────────────────────────

    async def enabled(self, budget_id: uuid.UUID) -> bool:
        prefs = (await self.guide.state(budget_id)).get(PREFS_KEY, {})
        return bool(prefs.get("wishlist", DEFAULT_PREFS["wishlist"]))

    async def _require_enabled(self, budget_id: uuid.UUID) -> None:
        if not await self.enabled(budget_id):
            raise InvariantViolation("The wishlist is switched off for this budget")

    async def settings(self, budget_id: uuid.UUID) -> dict[str, int]:
        stored = (await self.guide.state(budget_id)).get(SETTINGS_KEY, {})
        return {
            **DEFAULT_SETTINGS,
            **{k: int(v) for k, v in stored.items() if k in DEFAULT_SETTINGS},
        }

    async def set_settings(self, budget_id: uuid.UUID, changes: dict[str, int]) -> dict[str, int]:
        merged = {**(await self.settings(budget_id)), **changes}
        await self.guide.set_state(budget_id, SETTINGS_KEY, merged)
        return merged

    async def ensure_group(self, budget_id: uuid.UUID) -> CategoryGroup:
        return await self.groups.ensure_system_group(budget_id, "wishlist")

    # ── reading ──────────────────────────────────────────────────────────────

    async def overview(self, budget_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        if not await self.enabled(budget_id):
            return {
                "enabled": False,
                "items": [],
                "history": [],
                "projects": [],
                "still_wanted": {"count": 0, "of": 0, "months": STILL_WANTED_MONTHS},
                "review_due_count": 0,
                "settings": await self.settings(budget_id),
                "priority_limit": PRIORITY_LIMIT,
                "drains": None,
            }
        await self.ensure_group(budget_id)
        return await self._build(budget_id, today)

    async def _build(self, budget_id: uuid.UUID, today: date) -> dict[str, Any]:
        settings = await self.settings(budget_id)
        projects = await self._projects(budget_id)
        items = await self._items(budget_id)
        names = {
            c.id: c.name for c in await self.categories.get_all(budget_id, include_archived=True)
        }
        project_inputs = {p.id: ProjectInput(id=p.id, category_id=p.category_id) for p in projects}
        wish_inputs = [self._input(i) for i in items]

        envelopes: set[uuid.UUID] = set()
        for w in wish_inputs:
            if w.status != "open":
                continue
            envelope = effective_category(w, project_inputs)
            if envelope is not None and envelope in names:
                envelopes.add(envelope)
        funding: dict[uuid.UUID, Funding] = {e: await self._funding(e, today) for e in envelopes}
        reach = reach_for(wish_inputs, project_inputs, funding, today)
        targets = {
            t.category_id: t
            for t in await self.targets.repo.get_by_category_ids(
                [i.category_id for i in items if i.owns_envelope and i.category_id]
            )
        }

        out_items = [
            self._item_out(i, project_inputs, names, reach, targets, settings, today) for i in items
        ]
        open_items = [o for o in out_items if o["status"] == "open"]
        history = [o for o in out_items if o["status"] != "open"]
        count, of = still_wanted(wish_inputs, today)
        drains = await self._drains(
            budget_id, today, envelopes, funding, items, project_inputs, names
        )
        return {
            "enabled": True,
            "items": open_items,
            "history": history,
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "category_id": p.category_id,
                    "category_name": names.get(p.category_id) if p.category_id else None,
                    "notes": p.notes,
                    "sort_order": p.sort_order,
                    "summary": project_summary(p.id, wish_inputs, reach).__dict__,
                }
                for p in projects
            ],
            "still_wanted": {"count": count, "of": of, "months": STILL_WANTED_MONTHS},
            "review_due_count": sum(1 for o in open_items if o["review_due"]),
            "settings": settings,
            "priority_limit": PRIORITY_LIMIT,
            "drains": drains,
        }

    async def _drains(
        self,
        budget_id: uuid.UUID,
        today: date,
        envelopes: set[uuid.UUID],
        funding: dict[uuid.UUID, Funding],
        items: list[WishlistItem],
        projects: dict[uuid.UUID, ProjectInput],
        names: dict[uuid.UUID, str],
    ) -> dict[str, Any]:
        """This month's moves out of the envelopes that fund open wishes, and
        how much further away each wish on that envelope now is."""
        month = month_start(today)
        moves = await self.moves.outflows_from(budget_id, list(envelopes), month, month)
        shaped = shape_drains(moves, names)
        wishes_on: dict[uuid.UUID, list[WishlistItem]] = {}
        for item in items:
            if item.status != "open":
                continue
            envelope = effective_category(self._input(item), projects)
            if envelope is not None:
                wishes_on.setdefault(envelope, []).append(item)
        rows = []
        for drain in shaped:
            fund = funding.get(drain.from_category_id)
            pace = fund.monthly_rate if fund else None
            rows.append(
                {
                    **asdict(drain),
                    "affected": [
                        {
                            "item_id": w.id,
                            "name": w.name,
                            "months_further": drain_impact(drain.amount, pace),
                        }
                        for w in wishes_on.get(drain.from_category_id, [])
                    ],
                }
            )
        return {"month": month, "total": drains_total(shaped), "moves": rows}

    @staticmethod
    def _input(item: WishlistItem) -> WishInput:
        return WishInput(
            id=item.id,
            project_id=item.project_id,
            category_id=item.category_id,
            cost=item.cost,
            priority=item.priority,
            created_at=item.created_at.date(),
            status=item.status,
        )

    def _item_out(
        self,
        item: WishlistItem,
        projects: dict[uuid.UUID, ProjectInput],
        names: dict[uuid.UUID, str],
        reach: dict[uuid.UUID, Reach],
        targets: dict,
        settings: dict[str, int],
        today: date,
    ) -> dict[str, Any]:
        wish = self._input(item)
        envelope = effective_category(wish, projects)
        if envelope is not None and envelope not in names:
            envelope = None  # deleted underneath the wish: reads as unlinked
        mode = "own" if item.owns_envelope and envelope else ("existing" if envelope else "none")
        target = targets.get(item.category_id) if item.owns_envelope else None
        r = reach.get(item.id)
        return {
            "id": item.id,
            "project_id": item.project_id,
            "name": item.name,
            "url": item.url,
            "notes": item.notes,
            "cost": item.cost,
            "priority": item.priority,
            "is_priority": item.is_priority,
            "status": item.status,
            "funding": {
                "mode": mode,
                "category_id": envelope,
                "category_name": names.get(envelope) if envelope else None,
                "inherited": envelope is not None and item.category_id is None,
                "owns_envelope": item.owns_envelope,
                "target_date": target.target_date if target else None,
            },
            "cooling_until": item.cooling_until,
            "cooling": item.cooling_until is not None and item.cooling_until > today,
            "last_affirmed_at": item.last_affirmed_at,
            "review_due": item.status == "open"
            and review_due(
                wish.created_at,
                item.last_affirmed_at.date() if item.last_affirmed_at else None,
                item.cooling_until,
                settings["review_after_days"],
                today,
            ),
            "done_at": item.done_at,
            "created_at": item.created_at,
            "reach": r.__dict__ if r else None,
        }

    async def _funding(self, category_id: uuid.UUID, today: date) -> Funding:
        month = month_start(today)
        balance = await self.budget.get_category_balance(category_id, month)
        target = await self.targets.get(category_id)
        pace = self.targets.monthly_pace(target, balance.available, today) if target else None
        if pace is None:
            rows = await self.assignments.get_for_category(category_id, through_month=month)
            average = trailing_average({a.month: a.assigned for a in rows}, month)
            pace = average if average > Decimal("0") else None
        return Funding(available=balance.available, monthly_rate=pace)

    async def _projects(self, budget_id: uuid.UUID) -> list[WishlistProject]:
        rows = await self.session.execute(
            select(WishlistProject)
            .where(WishlistProject.budget_id == budget_id, ~WishlistProject.is_deleted)
            .order_by(WishlistProject.sort_order, WishlistProject.name)
        )
        return list(rows.scalars().all())

    async def _items(self, budget_id: uuid.UUID) -> list[WishlistItem]:
        rows = await self.session.execute(
            select(WishlistItem)
            .where(WishlistItem.budget_id == budget_id, ~WishlistItem.is_deleted)
            .order_by(WishlistItem.priority, WishlistItem.created_at)
        )
        return list(rows.scalars().all())

    async def item_out(self, budget_id: uuid.UUID, item_id: uuid.UUID) -> dict[str, Any]:
        built = await self._build(budget_id, date.today())
        for row in built["items"] + built["history"]:
            if row["id"] == item_id:
                return row
        raise NotFoundError("Wish", str(item_id))

    async def project_out(self, budget_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, Any]:
        built = await self._build(budget_id, date.today())
        for row in built["projects"]:
            if row["id"] == project_id:
                return row
        raise NotFoundError("Project", str(project_id))

    # ── wishes ───────────────────────────────────────────────────────────────

    async def _get_item(self, budget_id: uuid.UUID, item_id: uuid.UUID) -> WishlistItem:
        item = await self.session.get(WishlistItem, item_id)
        if item is None or item.budget_id != budget_id or item.is_deleted:
            raise NotFoundError("Wish", str(item_id))
        return item

    async def _get_project(self, budget_id: uuid.UUID, project_id: uuid.UUID) -> WishlistProject:
        project = await self.session.get(WishlistProject, project_id)
        if project is None or project.budget_id != budget_id or project.is_deleted:
            raise NotFoundError("Project", str(project_id))
        return project

    async def _checked_category(
        self, budget_id: uuid.UUID, category_id: uuid.UUID | None
    ) -> uuid.UUID:
        if category_id is None:
            raise InvariantViolation("Pick a category to fund this from")
        category = await self.categories.get(category_id)
        if category is None or category.budget_id != budget_id or category.is_deleted:
            raise NotFoundError("Category", str(category_id))
        return category.id

    async def _create_envelope(
        self, budget_id: uuid.UUID, name: str, cost: Decimal, want_by: date | None
    ) -> Category:
        group = await self.ensure_group(budget_id)
        clash = (
            await self.session.execute(
                select(Category.id).where(
                    Category.budget_id == budget_id,
                    func.lower(Category.name) == name.lower(),
                    Category.is_deleted == False,  # noqa: E712
                )
            )
        ).first()
        if clash is not None:
            raise InvariantViolation(
                f"A category named '{name}' already exists — pick a different name, "
                "or fund the wish from that category"
            )
        # The repository puts a new category last in its group.
        category = await self.categories.create(
            budget_id=budget_id,
            category_group_id=group.id,
            name=name,
        )
        # The envelope and its goal are the wish's own side effects, recorded
        # into the caller's open batch so undoing the wish removes them too —
        # without the batch, ⌘Z peeled them off one keystroke at a time.
        await self.changes.record(
            budget_id=budget_id,
            entity_type="category",
            entity_id=category.id,
            action="create",
            after=snapshot("category", category),
        )
        await self.targets.upsert(
            category.id,
            "savings_balance",
            quantize_cents(cost),
            want_by,
            batch_id=self.changes.current_batch_id,
        )
        return category

    async def create(self, budget_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        await self._require_enabled(budget_id)
        today = date.today()
        settings = await self.settings(budget_id)
        funding = data.get("funding") or {}
        mode = funding.get("mode", "none")
        cost = quantize_cents(Decimal(data.get("cost") or 0))
        name = data["name"].strip()

        category_id: uuid.UUID | None = None
        owns = False
        # One batch: a wish born with its own envelope records the category,
        # the goal, and the wish as a unit, so one ⌘Z takes all three back.
        with self.changes.batch():
            if mode == "own":
                category_id = (
                    await self._create_envelope(budget_id, name, cost, funding.get("want_by"))
                ).id
                owns = True
            elif mode == "existing":
                category_id = await self._checked_category(budget_id, funding.get("category_id"))

            project_id = data.get("project_id")
            if project_id is not None:
                await self._get_project(budget_id, project_id)

            priority = data.get("priority")
            if priority is None:
                last = (
                    await self.session.execute(
                        select(func.coalesce(func.max(WishlistItem.priority), -1)).where(
                            WishlistItem.budget_id == budget_id
                        )
                    )
                ).scalar_one()
                priority = int(last) + 1

            cooling_days = data.get("cooling_days")
            if cooling_days is None:
                cooling_days = settings["cooling_days"]

            item = WishlistItem(
                budget_id=budget_id,
                project_id=project_id,
                name=name,
                url=data.get("url"),
                notes=data.get("notes"),
                cost=cost,
                category_id=category_id,
                owns_envelope=owns,
                priority=priority,
                status="open",
                cooling_until=cooling_until_for(today, cooling_days),
            )
            self.session.add(item)
            await self.session.flush()
            await self.changes.record(
                budget_id=budget_id,
                entity_type="wishlist_item",
                entity_id=item.id,
                action="create",
                after=snapshot("wishlist_item", item),
            )
        await self._sync_tags(budget_id, [await self._envelope_of(budget_id, item)])
        return await self.item_out(budget_id, item.id)

    async def update(
        self, budget_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        await self._require_enabled(budget_id)
        item = await self._get_item(budget_id, item_id)
        before = snapshot("wishlist_item", item)
        before_envelope = await self._envelope_of(budget_id, item)

        # One batch: a cost edit that moves the envelope's goal records both
        # rows as a unit, so one ⌘Z takes the pair back together.
        with self.changes.batch():
            if "name" in data:
                item.name = data["name"].strip()
            for key in ("url", "notes", "cooling_until"):
                if key in data:
                    setattr(item, key, data[key])
            if "priority" in data and data["priority"] is not None:
                item.priority = int(data["priority"])
            if "cost" in data and data["cost"] is not None:
                item.cost = quantize_cents(Decimal(data["cost"]))
                if item.owns_envelope and item.category_id:
                    # One-way: the wish's cost sets the goal. The budget page may
                    # move the goal afterwards; the two are allowed to differ.
                    target = await self.targets.get(item.category_id)
                    await self.targets.upsert(
                        item.category_id,
                        target.target_type if target else "savings_balance",
                        item.cost,
                        target.target_date if target else None,
                        target.repeat_frequency if target else None,
                        batch_id=self.changes.current_batch_id,
                    )
            if "project_id" in data:
                if data["project_id"] is not None:
                    await self._get_project(budget_id, data["project_id"])
                item.project_id = data["project_id"]
            if "funding" in data and data["funding"] is not None:
                mode = data["funding"].get("mode", "none")
                if mode == "own":
                    raise InvariantViolation(
                        "An envelope of its own is chosen when a wish is added"
                    )
                if mode == "existing":
                    item.category_id = await self._checked_category(
                        budget_id, data["funding"].get("category_id")
                    )
                else:
                    item.category_id = None
                item.owns_envelope = False
            if "status" in data and data["status"] is not None:
                self._apply_status(item, data["status"])
            if "is_priority" in data and data["is_priority"] is not None:
                await self._apply_priority(budget_id, item, bool(data["is_priority"]))

            await self.session.flush()
            after = snapshot("wishlist_item", item)
            if snapshots_match(after, before):  # non-empty diff — something changed
                await self.changes.record(
                    budget_id=budget_id,
                    entity_type="wishlist_item",
                    entity_id=item.id,
                    action="update",
                    before=before,
                    after=after,
                )
        after_envelope = await self._envelope_of(budget_id, item)
        await self._sync_tags(budget_id, [before_envelope, after_envelope])
        return await self.item_out(budget_id, item.id)

    @staticmethod
    def _apply_status(item: WishlistItem, status: str) -> None:
        if status not in STATUSES:
            raise InvariantViolation(f"Unknown status '{status}'")
        item.status = status
        item.done_at = date.today() if status == "done" else None
        if status != "open":
            # Only an open wish holds a spotlight slot; clearing here is what
            # keeps a reopened wish from silently busting the cap.
            item.is_priority = False

    async def _apply_priority(self, budget_id: uuid.UUID, item: WishlistItem, pinned: bool) -> None:
        """Pin or unpin a wish as a top priority.

        The cap is the rule, not the strip's rendering: a full spotlight
        refuses the pin rather than silently displacing one, so what is shown
        is always exactly what someone chose.
        """
        if pinned and not item.is_priority:
            if item.status != "open":
                raise InvariantViolation("Only an open wish can be a top priority")
            taken = await self.session.scalar(
                select(func.count())
                .select_from(WishlistItem)
                .where(
                    WishlistItem.budget_id == budget_id,
                    WishlistItem.status == "open",
                    WishlistItem.is_priority,
                    # A deleted wish keeps its pin in the snapshot (undo
                    # restores it faithfully) but holds no slot while gone.
                    ~WishlistItem.is_deleted,
                    WishlistItem.id != item.id,
                )
            )
            if (taken or 0) >= PRIORITY_LIMIT:
                raise InvariantViolation(
                    f"Top priorities are full ({PRIORITY_LIMIT}) — unpin one first"
                )
        item.is_priority = pinned

    async def delete(self, budget_id: uuid.UUID, item_id: uuid.UUID) -> dict[str, Any]:
        await self._require_enabled(budget_id)
        item = await self._get_item(budget_id, item_id)
        envelope_out = None
        if item.owns_envelope and item.category_id is not None:
            category = await self.categories.get(item.category_id)
            if category is not None and not category.is_deleted:
                balance = await self.budget.get_category_balance(
                    category.id, month_start(date.today())
                )
                envelope_out = {
                    "category_id": category.id,
                    "name": category.name,
                    "available": balance.available,
                }
        envelope = await self._envelope_of(budget_id, item)
        # Soft, never session.delete: a hard-deleted row is beyond undo's
        # reach — the flag is what lets ⌘Z bring the wish back exactly.
        before = snapshot("wishlist_item", item)
        item.is_deleted = True
        await self.session.flush()
        await self.changes.record(
            budget_id=budget_id,
            entity_type="wishlist_item",
            entity_id=item.id,
            action="delete",
            before=before,
        )
        await self._sync_tags(budget_id, [envelope])
        return {"envelope": envelope_out}

    async def affirm(self, budget_id: uuid.UUID, item_id: uuid.UUID) -> None:
        await self._require_enabled(budget_id)
        item = await self._get_item(budget_id, item_id)
        before = snapshot("wishlist_item", item)
        item.last_affirmed_at = datetime.now(UTC)
        await self.session.flush()
        await self.changes.record(
            budget_id=budget_id,
            entity_type="wishlist_item",
            entity_id=item.id,
            action="update",
            before=before,
            after=snapshot("wishlist_item", item),
        )

    async def reorder_items(self, budget_id: uuid.UUID, item_ids: list[uuid.UUID]) -> None:
        await self._require_enabled(budget_id)
        ordered = await self._items(budget_id)
        items = {i.id: i for i in ordered}
        if len(set(item_ids)) != len(item_ids) or set(item_ids) - items.keys():
            raise InvariantViolation("Reorder must name this budget's wishes, each once")
        for wish_id, position in renumber(item_ids).items():
            items[wish_id].priority = position
        await self.session.flush()
        # Subject = the budget (the container), like a group reorder;
        # `_collection` tells the undo which of the budget's lists to renumber.
        before_ids = [str(i.id) for i in ordered]
        after_ids = [str(i) for i in item_ids]
        if before_ids != after_ids:
            await self.changes.record(
                budget_id=budget_id,
                entity_type="wishlist",
                entity_id=budget_id,
                action="reorder",
                before={"_order": before_ids, "_collection": "wishlist_items"},
                after={"_order": after_ids, "_collection": "wishlist_items"},
            )

    # ── projects ─────────────────────────────────────────────────────────────

    async def create_project(self, budget_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        await self._require_enabled(budget_id)
        category_id = data.get("category_id")
        if category_id is not None:
            category_id = await self._checked_category(budget_id, category_id)
        last = (
            await self.session.execute(
                select(func.coalesce(func.max(WishlistProject.sort_order), -1)).where(
                    WishlistProject.budget_id == budget_id
                )
            )
        ).scalar_one()
        project = WishlistProject(
            budget_id=budget_id,
            name=data["name"].strip(),
            category_id=category_id,
            notes=data.get("notes"),
            sort_order=int(last) + 1,
        )
        self.session.add(project)
        await self.session.flush()
        await self.changes.record(
            budget_id=budget_id,
            entity_type="wishlist_project",
            entity_id=project.id,
            action="create",
            after=snapshot("wishlist_project", project),
        )
        await self._sync_tags(budget_id, [category_id])
        return await self.project_out(budget_id, project.id)

    async def update_project(
        self, budget_id: uuid.UUID, project_id: uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        await self._require_enabled(budget_id)
        project = await self._get_project(budget_id, project_id)
        before_snapshot = snapshot("wishlist_project", project)
        before = project.category_id
        if "name" in data and data["name"] is not None:
            project.name = data["name"].strip()
        if "notes" in data:
            project.notes = data["notes"]
        if "category_id" in data:
            project.category_id = (
                await self._checked_category(budget_id, data["category_id"])
                if data["category_id"] is not None
                else None
            )
        await self.session.flush()
        after_snapshot = snapshot("wishlist_project", project)
        if snapshots_match(after_snapshot, before_snapshot):
            await self.changes.record(
                budget_id=budget_id,
                entity_type="wishlist_project",
                entity_id=project.id,
                action="update",
                before=before_snapshot,
                after=after_snapshot,
            )
        await self._sync_tags(budget_id, [before, project.category_id])
        return await self.project_out(budget_id, project.id)

    async def delete_project(self, budget_id: uuid.UUID, project_id: uuid.UUID) -> None:
        """Ungroup its wishes and remove the project; the wishes stay."""
        await self._require_enabled(budget_id)
        project = await self._get_project(budget_id, project_id)
        envelope = project.category_id
        # `_wish_ids` is undo bookkeeping: the wishes this delete orphaned,
        # so the undo can re-point exactly those — and only those that are
        # still loose when it runs.
        orphaned: list[str] = []
        for item in await self._items(budget_id):
            if item.project_id == project_id:
                item.project_id = None
                orphaned.append(str(item.id))
        before = snapshot("wishlist_project", project)
        project.is_deleted = True
        await self.session.flush()
        await self.changes.record(
            budget_id=budget_id,
            entity_type="wishlist_project",
            entity_id=project.id,
            action="delete",
            before={**before, "_wish_ids": orphaned},
        )
        await self._sync_tags(budget_id, [envelope])

    async def reorder_projects(self, budget_id: uuid.UUID, project_ids: list[uuid.UUID]) -> None:
        await self._require_enabled(budget_id)
        ordered = await self._projects(budget_id)
        projects = {p.id: p for p in ordered}
        if len(set(project_ids)) != len(project_ids) or set(project_ids) - projects.keys():
            raise InvariantViolation("Reorder must name this budget's projects, each once")
        for project_id, position in renumber(project_ids).items():
            projects[project_id].sort_order = position
        await self.session.flush()
        before_ids = [str(p.id) for p in ordered]
        after_ids = [str(p) for p in project_ids]
        if before_ids != after_ids:
            await self.changes.record(
                budget_id=budget_id,
                entity_type="wishlist",
                entity_id=budget_id,
                action="reorder",
                before={"_order": before_ids, "_collection": "wishlist_projects"},
                after={"_order": after_ids, "_collection": "wishlist_projects"},
            )

    # ── the derived tag ──────────────────────────────────────────────────────

    async def _envelope_of(self, budget_id: uuid.UUID, item: WishlistItem) -> uuid.UUID | None:
        projects = {
            p.id: ProjectInput(id=p.id, category_id=p.category_id)
            for p in await self._projects(budget_id)
        }
        return effective_category(self._input(item), projects)

    async def _sync_tags(self, budget_id: uuid.UUID, category_ids: list[uuid.UUID | None]) -> None:
        """The `wishlist` tag is on an envelope iff an open wish draws on it.

        Derived from the link rather than kept alongside it, so a report that
        filters by the tag cannot disagree with the list.
        """
        wanted = {c for c in category_ids if c is not None}
        if not wanted:
            return
        tag = await self.tags.get_system_tag(budget_id, "wishlist")
        if tag is None:
            await seed_system_tags(self.session, budget_id)
            tag = await self.tags.get_system_tag(budget_id, "wishlist")
            if tag is None:
                return
        projects = {
            p.id: ProjectInput(id=p.id, category_id=p.category_id)
            for p in await self._projects(budget_id)
        }
        funded = {
            effective_category(self._input(i), projects)
            for i in await self._items(budget_id)
            if i.status == "open"
        }
        for category_id in wanted:
            if category_id in funded:
                await self.tags.add_category_tag(category_id, tag.id)
            else:
                await self.tags.remove_category_tag(category_id, tag.id)
            # The association changed underneath any loaded Category: expire
            # its collection so a read in this same session sees the change.
            category = await self.session.get(Category, category_id)
            if category is not None:
                self.session.expire(category, ["tags"])
