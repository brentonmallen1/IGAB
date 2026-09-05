"""Category plans: CRUD orchestration and the apply-targets classification.

The planner's display arithmetic (even splits, per-paycheck totals) lives in
the client's pure module; the server stores documents and owns the one
decision that touches the real budget — how a plan's rows map onto categories
and targets. That classification exists once, in `_classify`: the preview
endpoint reports it and the apply endpoint executes it, so what the
confirmation sheet says is exactly what happens.

Rows resolve in this order:

- a row with no amount (or no name and no link) is a **draft** — reported,
  never applied, never an error; autosave stores half-typed rows on purpose.
- a **linked** row names a category by id. Foreign, deleted, or
  non-assignable links are reported as invalid, not applied — the served
  ``is_assignable`` rule decides, the same one every picker uses.
- a **free-form** row is matched by name against assignable categories (and
  the "Planned" group's own rows, archived included, since creating beside an
  archived namesake would violate the per-group live-name index). A match is
  ADOPTED — the row becomes linked — following `ensure_system_group`'s
  convention of adopting rather than colliding. No match creates the category
  in the "Planned" group.
- rows resolving to one category are summed; the target set is always
  ``monthly_funding``. A target of any other type is KEPT and flagged — the
  planner must not quietly flatten a savings-balance goal into a monthly one.

Nothing here writes the change log: targets and category creation are not
change-logged anywhere today (see `TargetService.upsert` and the wishlist's
envelope creation), and plan CRUD is scratchpad state like `guide_state`.
"""

import copy
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Category, CategoryGroup, CategoryPlan
from igab.domain.exceptions import InvariantViolation, NotFoundError
from igab.domain.money import quantize_cents
from igab.repositories.category_plan_repo import CategoryPlanRepository
from igab.repositories.category_repo import CategoryGroupRepository, CategoryRepository
from igab.repositories.target_repo import TargetRepository
from igab.services.change_log import ChangeRecorder, snapshot, snapshots_match
from igab.services.target_service import TargetService

#: Where apply files categories the budget does not have yet. A plain group —
#: no system_key protection; once created, it is the user's like any other.
PLANNED_GROUP_NAME = "Planned"
MAX_PLANS = 20


def _default_payload() -> dict[str, Any]:
    # Matches the default cadence: biweekly implies two paychecks, and the
    # client renders columns straight from this array.
    return {
        "schema_version": 1,
        "monthly_income_cents": 0,
        "cadence": "biweekly",
        "paycheck_count_override": None,
        "paychecks": [
            {"id": str(uuid.uuid4()), "income_override_cents": None, "items": []},
            {"id": str(uuid.uuid4()), "income_override_cents": None, "items": []},
        ],
    }


class CategoryPlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = CategoryPlanRepository(session)
        self.categories = CategoryRepository(session)
        self.groups = CategoryGroupRepository(session)
        self.targets = TargetService(TargetRepository(session))
        # Every mutation records (change_log.py). Plans are hard rows, and
        # apply-targets creates covered entities (categories, a group) that
        # every OTHER route records — bypassing the log here made the
        # Activity feed lie by omission.
        self.changes = ChangeRecorder(session)

    async def _record(
        self,
        plan: CategoryPlan,
        action: str,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        await self.changes.record(
            budget_id=plan.budget_id,
            entity_type="category_plan",
            entity_id=plan.id,
            action=action,
            before=before,
            after=after,
        )

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def list_plans(self, budget_id: uuid.UUID) -> list[CategoryPlan]:
        return await self.plans.get_all(budget_id)

    async def get(self, budget_id: uuid.UUID, plan_id: uuid.UUID) -> CategoryPlan:
        plan = await self.plans.get_for_budget(budget_id, plan_id)
        if plan is None:
            raise NotFoundError("category_plan", str(plan_id))
        return plan

    async def create(
        self, budget_id: uuid.UUID, name: str | None, payload: dict[str, Any] | None
    ) -> CategoryPlan:
        await self._require_room(budget_id)
        if name is not None:
            name = name.strip()
            if not name:
                raise InvariantViolation("A plan needs a name")
            if await self.plans.name_exists(budget_id, name):
                raise InvariantViolation(f"A plan named '{name}' already exists")
        else:
            name = await self._default_name(budget_id)
        plan = await self.plans.create(
            budget_id=budget_id, name=name, payload=payload or _default_payload()
        )
        await self._record(plan, "create", after=snapshot("category_plan", plan))
        return plan

    async def update_payload(
        self, budget_id: uuid.UUID, plan_id: uuid.UUID, payload: dict[str, Any]
    ) -> CategoryPlan:
        plan = await self.get(budget_id, plan_id)
        before = snapshot("category_plan", plan)
        plan = await self.plans.update(plan.id, payload=payload)
        after = snapshot("category_plan", plan)
        if snapshots_match(after, before):  # non-empty diff — something changed
            await self._record(plan, "update", before=before, after=after)
        return plan

    async def rename(self, budget_id: uuid.UUID, plan_id: uuid.UUID, name: str) -> CategoryPlan:
        plan = await self.get(budget_id, plan_id)
        name = name.strip()
        if not name:
            raise InvariantViolation("A plan needs a name")
        if name.lower() != plan.name.lower() and await self.plans.name_exists(budget_id, name):
            raise InvariantViolation(f"A plan named '{name}' already exists")
        before = snapshot("category_plan", plan)
        plan = await self.plans.update(plan.id, name=name)
        after = snapshot("category_plan", plan)
        if snapshots_match(after, before):
            await self._record(plan, "update", before=before, after=after)
        return plan

    async def duplicate(
        self, budget_id: uuid.UUID, plan_id: uuid.UUID, name: str | None
    ) -> CategoryPlan:
        plan = await self.get(budget_id, plan_id)
        await self._require_room(budget_id)
        if name is not None:
            name = name.strip()
            if not name:
                raise InvariantViolation("A plan needs a name")
            if await self.plans.name_exists(budget_id, name):
                raise InvariantViolation(f"A plan named '{name}' already exists")
        else:
            name = await self._copy_name(budget_id, plan.name)
        # Ids are copied verbatim: they only need uniqueness within one plan,
        # and keeping them means a duplicated scenario diffs cleanly.
        copied = await self.plans.create(
            budget_id=budget_id, name=name, payload=copy.deepcopy(plan.payload)
        )
        await self._record(copied, "create", after=snapshot("category_plan", copied))
        return copied

    async def delete(self, budget_id: uuid.UUID, plan_id: uuid.UUID) -> None:
        plan = await self.get(budget_id, plan_id)
        await self._record(plan, "delete", before=snapshot("category_plan", plan))
        await self.plans.delete(plan)

    async def _require_room(self, budget_id: uuid.UUID) -> None:
        if await self.plans.count(budget_id) >= MAX_PLANS:
            raise InvariantViolation(
                f"A budget keeps at most {MAX_PLANS} plans — delete one to make room"
            )

    async def _default_name(self, budget_id: uuid.UUID) -> str:
        n = await self.plans.count(budget_id) + 1
        while await self.plans.name_exists(budget_id, f"Plan {n}"):
            n += 1
        return f"Plan {n}"

    async def _copy_name(self, budget_id: uuid.UUID, base: str) -> str:
        def fit(suffix: str) -> str:
            return base[: 120 - len(suffix)] + suffix

        candidate = fit(" (copy)")
        k = 2
        while await self.plans.name_exists(budget_id, candidate):
            candidate = fit(f" (copy {k})")
            k += 1
        return candidate

    # ── apply targets ─────────────────────────────────────────────────────

    async def preview_apply(self, budget_id: uuid.UUID, plan_id: uuid.UUID) -> dict[str, Any]:
        plan = await self.get(budget_id, plan_id)
        entries, _ = await self._classify(budget_id, plan.payload)
        return self._report(entries)

    async def apply(self, budget_id: uuid.UUID, plan_id: uuid.UUID) -> dict[str, Any]:
        plan = await self.get(budget_id, plan_id)
        payload = copy.deepcopy(plan.payload)
        entries, planned_group = await self._classify(budget_id, payload)

        # item id → (category id, canonical name), written back below
        links: dict[str, tuple[str, str]] = {}
        # One batch: everything apply conjures — the Planned group, the
        # categories, their goals, and the plan's own link-back — undoes as
        # one unit. Target records ride the same batch through their own
        # recorder (batch_id is just a column).
        with self.changes.batch() as batch_id:
            plan_before = snapshot("category_plan", plan)
            for entry in entries:
                kind = entry["kind"]
                if kind == "create_category":
                    if planned_group is None:
                        planned_group = await self._ensure_planned_group(budget_id)
                        # _ensure only ever creates (adoption happened in
                        # _classify), so this is always a fresh row.
                        await self.changes.record(
                            budget_id=budget_id,
                            entity_type="category_group",
                            entity_id=planned_group.id,
                            action="create",
                            after=snapshot("category_group", planned_group),
                        )
                    category = await self.categories.create(
                        budget_id=budget_id,
                        category_group_id=planned_group.id,
                        name=entry["name"],
                    )
                    entry["category_id"] = category.id
                    await self.changes.record(
                        budget_id=budget_id,
                        entity_type="category",
                        entity_id=category.id,
                        action="create",
                        after=snapshot("category", category),
                    )
                    await self.targets.upsert(
                        category.id, "monthly_funding", entry["amount"], batch_id=batch_id
                    )
                elif kind in ("set_target", "update_target"):
                    await self.targets.upsert(
                        entry["category_id"], "monthly_funding", entry["amount"], batch_id=batch_id
                    )
                if entry["category_id"] is not None and kind not in (
                    "skip_invalid_link",
                    "skip_draft",
                ):
                    # Adopted and created rows become linked; every resolved row
                    # refreshes its name snapshot to the category's canonical one.
                    for item_id in entry["item_ids"]:
                        links[item_id] = (str(entry["category_id"]), entry["name"])

            if links:
                for paycheck in payload.get("paychecks", []):
                    for item in paycheck.get("items", []):
                        linked = links.get(item.get("id"))
                        if linked is not None:
                            item["category_id"], item["name"] = linked
                plan = await self.plans.update(plan.id, payload=payload)
                plan_after = snapshot("category_plan", plan)
                if snapshots_match(plan_after, plan_before):
                    await self._record(plan, "update", before=plan_before, after=plan_after)

        report = self._report(entries)
        report["plan"] = plan
        return report

    @staticmethod
    def _report(entries: list[dict[str, Any]]) -> dict[str, Any]:
        def count(kind: str) -> int:
            return sum(1 for e in entries if e["kind"] == kind)

        return {
            "entries": entries,
            "targets_set": count("set_target"),
            "targets_updated": count("update_target"),
            "categories_created": count("create_category"),
            "skipped_existing_type": count("skip_existing_type"),
            "skipped_invalid_link": count("skip_invalid_link"),
            "skipped_draft": count("skip_draft"),
        }

    async def _classify(
        self, budget_id: uuid.UUID, payload: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], CategoryGroup | None]:
        """Every row's fate, in first-appearance order. Read-only."""
        categories = await self.categories.get_all(budget_id, include_archived=True)
        by_id = {c.id: c for c in categories}
        planned_group = await self._find_planned_group(budget_id)

        # Free-form rows adopt by name. Assignable categories are fair game;
        # so are the Planned group's own rows even when archived, because
        # creating beside an archived namesake would violate the per-group
        # live-name unique index. First (group, sort) occurrence wins.
        adopt_by_name: dict[str, Category] = {}
        for c in categories:
            eligible = c.is_assignable or (
                planned_group is not None and c.category_group_id == planned_group.id
            )
            if eligible and c.name.lower() not in adopt_by_name:
                adopt_by_name[c.name.lower()] = c

        entries: list[dict[str, Any]] = []
        # Rows resolving to the same category (or the same new name) merge
        # into one entry; `sums` indexes those merged entries.
        sums: dict[Any, dict[str, Any]] = {}

        def merged(key: Any, name: str, category_id: uuid.UUID | None) -> dict[str, Any]:
            entry = sums.get(key)
            if entry is None:
                entry = {
                    "kind": "",  # decided below, once amounts are summed
                    "name": name,
                    "category_id": category_id,
                    "cents": 0,
                    "amount": None,
                    "existing_target_type": None,
                    "item_ids": [],
                }
                sums[key] = entry
                entries.append(entry)
            return entry

        for paycheck in payload.get("paychecks", []):
            for item in paycheck.get("items", []):
                item_id = item.get("id")
                cents = item.get("amount_cents")
                raw_link = item.get("category_id")
                name = (item.get("name") or "").strip()

                if cents is None or (raw_link is None and not name):
                    entries.append(
                        {
                            "kind": "skip_draft",
                            "name": name,
                            "category_id": None,
                            "amount": None,
                            "existing_target_type": None,
                            "item_ids": [item_id],
                        }
                    )
                    continue

                if raw_link is not None:
                    category = by_id.get(uuid.UUID(raw_link))
                    if category is None or not category.is_assignable:
                        entries.append(
                            {
                                "kind": "skip_invalid_link",
                                "name": category.name if category is not None else name,
                                "category_id": None,
                                "amount": None,
                                "existing_target_type": None,
                                "item_ids": [item_id],
                            }
                        )
                        continue
                else:
                    category = adopt_by_name.get(name.lower())

                if category is not None:
                    entry = merged(category.id, category.name, category.id)
                else:
                    entry = merged(("create", name.lower()), name, None)
                entry["cents"] += cents
                entry["item_ids"].append(item_id)

        for entry in entries:
            if entry["kind"]:
                continue  # a per-row skip, already decided
            entry["amount"] = quantize_cents(Decimal(entry.pop("cents")) / 100)
            if entry["category_id"] is None:
                entry["kind"] = "create_category"
                continue
            target = await self.targets.get(entry["category_id"])
            if target is None:
                entry["kind"] = "set_target"
            elif target.target_type == "monthly_funding":
                entry["kind"] = "update_target"
            else:
                entry["kind"] = "skip_existing_type"
                entry["existing_target_type"] = target.target_type
                entry["amount"] = None
        for entry in entries:
            entry.pop("cents", None)

        return entries, planned_group

    async def _find_planned_group(self, budget_id: uuid.UUID) -> CategoryGroup | None:
        result = await self.session.execute(
            select(CategoryGroup).where(
                CategoryGroup.budget_id == budget_id,
                func.lower(CategoryGroup.name) == PLANNED_GROUP_NAME.lower(),
                CategoryGroup.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalars().first()

    async def _ensure_planned_group(self, budget_id: uuid.UUID) -> CategoryGroup:
        # Adopt a live group the user already named "Planned" rather than
        # colliding with the live-name unique index; _find_planned_group is
        # that adoption check, so reaching here means it does not exist.
        return await self.groups.create(budget_id=budget_id, name=PLANNED_GROUP_NAME)
