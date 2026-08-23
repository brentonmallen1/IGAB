"""The Guide's one entry point.

`api/v1/guide.py` talks to this and nothing else, which is what keeps the rest
of the package free to change without touching the HTTP layer.
"""

import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, Liability
from igab.guide.bindings import Resolution, resolve_all
from igab.guide.concepts import (
    CONCEPTS,
    CONCEPTS_BY_KEY,
    FULL_EMERGENCY_FUND_MONTHS_LOW,
    HIGH_INTEREST_APR,
    RETIREMENT_TARGET_RATE,
    STARTER_EMERGENCY_FUND,
)
from igab.guide.detection import Finding, GuideDetection
from igab.guide.repo import GuideRepository

#: Defaults for the two switches on the settings page. Both on: the roadmap is
#: far more useful when it knows the numbers, and every inference it makes is
#: explained and reversible.
DEFAULT_PREFS: dict[str, bool] = {"personalization": True, "checkup": True}

PREFS_KEY = "prefs"
STEP_PREFIX = "step:"


class GuideService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GuideRepository(session)
        self.detection = GuideDetection(session)

    # ── preferences ──────────────────────────────────────────────────────────

    async def preferences(self, budget_id: uuid.UUID) -> dict[str, bool]:
        stored = (await self.repo.state(budget_id)).get(PREFS_KEY, {})
        return {**DEFAULT_PREFS, **{k: bool(v) for k, v in stored.items()}}

    async def set_preferences(
        self, budget_id: uuid.UUID, changes: dict[str, bool]
    ) -> dict[str, bool]:
        current = await self.preferences(budget_id)
        merged = {**current, **changes}
        # Health findings are built from the same signals, so personalisation
        # off means checkup off. Stored that way rather than only hidden in the
        # UI, so nothing downstream has to remember the rule.
        if not merged.get("personalization", True):
            merged["checkup"] = False
        await self.repo.set_state(budget_id, PREFS_KEY, merged)
        return merged

    # ── step progress ────────────────────────────────────────────────────────

    async def progress(self, budget_id: uuid.UUID) -> dict[str, str]:
        state = await self.repo.state(budget_id)
        return {
            key[len(STEP_PREFIX) :]: value.get("state", "")
            for key, value in state.items()
            if key.startswith(STEP_PREFIX) and value.get("state")
        }

    async def set_step(self, budget_id: uuid.UUID, stage_id: str, state: str | None) -> None:
        key = f"{STEP_PREFIX}{stage_id}"
        if state is None:
            await self.repo.delete_state(budget_id, key)
        else:
            await self.repo.set_state(budget_id, key, {"state": state})

    # ── signals ──────────────────────────────────────────────────────────────

    async def signals(self, budget_id: uuid.UUID) -> dict[str, Any]:
        """Every concept, resolved and — where it applies — detected.

        With personalisation off this returns the concept list and nothing
        else: no detection query runs at all, which is what "off" has to mean
        for a household member who finds the whole thing stressful.
        """
        prefs = await self.preferences(budget_id)
        keys = [c.key for c in CONCEPTS]
        rows = await self.repo.bindings(budget_id)
        resolutions = resolve_all(keys, rows)

        if not prefs["personalization"]:
            return {
                "personalization": False,
                "concepts": [
                    {"key": key, "tracked": True, "source": "off", "met": None} for key in keys
                ],
            }

        essentials = await self._maybe_detect("essential_expenses", resolutions, budget_id)

        out: list[dict[str, Any]] = []
        for key in keys:
            resolution = resolutions[key]
            concept = CONCEPTS_BY_KEY[key]
            if not resolution.tracked:
                out.append(
                    {
                        "key": key,
                        "tracked": False,
                        "source": "dismissed",
                        "met": None,
                        "note": resolution.note,
                    }
                )
                continue
            if resolution.source == "answer":
                out.append(
                    {
                        "key": key,
                        "tracked": True,
                        "source": "answer",
                        "met": resolution.answer,
                        "reason": "you told us",
                        "note": resolution.note,
                    }
                )
                continue

            finding = await self._detect(key, resolution, budget_id)
            payload = self._present(concept.key, finding, resolution, essentials)
            out.append(payload)

        return {"personalization": True, "concepts": out}

    async def _maybe_detect(
        self, key: str, resolutions: dict[str, Resolution], budget_id: uuid.UUID
    ) -> Finding | None:
        resolution = resolutions.get(key)
        if resolution is None or not resolution.runs_detection:
            return None
        return await self._detect(key, resolution, budget_id)

    async def _detect(
        self, key: str, resolution: Resolution, budget_id: uuid.UUID
    ) -> Finding | None:
        bound = resolution.entities or None
        match key:
            case "budget_exists":
                return Finding(concept_key=key, met=True, reason="you have a budget")
            case "emergency_fund":
                return await self.detection.emergency_fund(budget_id, bound)
            case "essential_expenses":
                return await self.detection.essential_expenses(budget_id, bound)
            case "high_interest_debt":
                return await self.detection.high_interest_debt(budget_id)
            case "moderate_interest_debt":
                return await self.detection.moderate_interest_debt(budget_id)
            case "retirement_contributions":
                return await self.detection.retirement_contributions(budget_id, bound)
            case _:
                # employer_match, hsa, college_savings: nothing to detect.
                return None

    def _present(
        self,
        key: str,
        finding: Finding | None,
        resolution: Resolution,
        essentials: Finding | None,
    ) -> dict[str, Any]:
        """Fold detection and any self-reported amount into one answer."""
        detected = finding.value if finding else None
        external = resolution.external_amount
        total: Decimal | None
        if detected is None and external is None:
            total = None
        else:
            total = (detected or Decimal("0")) + (external or Decimal("0"))

        target = self._target(key, essentials)
        met = self._met(key, finding, resolution, total, target)

        return {
            "key": key,
            "tracked": True,
            "source": resolution.source,
            "met": met,
            "value": total,
            "detected_value": detected,
            "external_value": external,
            "external_declared": resolution.external_declared,
            "external_as_of": resolution.external_as_of,
            "target": target,
            "reason": finding.reason if finding else "",
            "entities": self._entities(finding, resolution),
            "gaps": finding.gaps if finding else [],
            "note": resolution.note,
        }

    def _target(self, key: str, essentials: Finding | None) -> Decimal | None:
        match key:
            case "emergency_fund":
                # Three months of real spending once we know it; the flat
                # starter figure until then.
                if essentials and essentials.value:
                    return essentials.value * FULL_EMERGENCY_FUND_MONTHS_LOW
                return Decimal(STARTER_EMERGENCY_FUND)
            case "retirement_contributions":
                return Decimal(RETIREMENT_TARGET_RATE)
            case "high_interest_debt" | "moderate_interest_debt":
                return Decimal("0")
            case _:
                return None

    def _met(
        self,
        key: str,
        finding: Finding | None,
        resolution: Resolution,
        total: Decimal | None,
        target: Decimal | None,
    ) -> bool | None:
        # A declaration with no figure is a complete answer: the user says it
        # is handled and we have no basis to argue.
        if resolution.external_declared and resolution.external_amount is None:
            return True
        if key in ("high_interest_debt", "moderate_interest_debt"):
            # "Met" here means the roadmap step is satisfied — no such debt.
            return None if finding is None else not finding.entities.get("liability")
        if total is None or target is None:
            return finding.met if finding else None
        return total >= target

    def _entities(self, finding: Finding | None, resolution: Resolution) -> dict[str, list[str]]:
        source = (
            {k: list(v) for k, v in resolution.entities.items()}
            if resolution.entities
            else (finding.entities if finding else {})
        )
        return {k: [str(i) for i in v] for k, v in source.items()}

    # ── candidates for the binding picker ────────────────────────────────────

    async def candidates(self, budget_id: uuid.UUID, concept_key: str) -> dict[str, list[dict]]:
        """What the user may point a concept at.

        Scoped to the entity types the concept accepts, so the picker never
        offers a liability as an emergency fund.
        """
        concept = CONCEPTS_BY_KEY[concept_key]
        out: dict[str, list[dict]] = {}

        if "category" in concept.binds_to:
            rows = (
                await self.session.execute(
                    select(Category.id, Category.name)
                    .where(
                        Category.budget_id == budget_id,
                        Category.is_deleted == False,  # noqa: E712
                        Category.is_hidden == False,  # noqa: E712
                    )
                    .order_by(Category.name)
                )
            ).all()
            out["category"] = [{"id": str(r.id), "name": r.name} for r in rows]

        if "account" in concept.binds_to:
            rows = (
                await self.session.execute(
                    select(Account.id, Account.name, Account.account_type)
                    .where(
                        Account.budget_id == budget_id,
                        Account.is_deleted == False,  # noqa: E712
                        Account.is_closed == False,  # noqa: E712
                    )
                    .order_by(Account.name)
                )
            ).all()
            out["account"] = [
                {"id": str(r.id), "name": r.name, "detail": r.account_type} for r in rows
            ]

        if "liability" in concept.binds_to:
            rows = (
                await self.session.execute(
                    select(Liability.id, Liability.name).where(Liability.budget_id == budget_id)
                )
            ).all()
            out["liability"] = [{"id": str(r.id), "name": r.name} for r in rows]

        return out

    # ── writing bindings ─────────────────────────────────────────────────────

    async def set_binding(
        self,
        budget_id: uuid.UUID,
        concept_key: str,
        *,
        mode: str,
        entity_ids: dict[str, list[uuid.UUID]] | None = None,
        answer: bool | None = None,
        amount: Decimal | None = None,
        note: str | None = None,
        external: bool = False,
        external_amount: Decimal | None = None,
    ) -> None:
        if mode == "auto":
            await self.repo.clear_concept(budget_id, concept_key)
            return

        rows: list[dict[str, Any]] = []
        if mode == "dismissed":
            rows.append({"mode": "dismissed", "note": note})
        elif mode == "answer":
            rows.append({"mode": "answer", "answer": answer, "note": note})
        else:
            for entity_type, ids in (entity_ids or {}).items():
                for entity_id in ids:
                    rows.append(
                        {"mode": "manual", "entity_type": entity_type, "entity_id": entity_id}
                    )
            if external:
                rows.append(
                    {
                        "mode": "external",
                        "amount": external_amount if external_amount is not None else amount,
                        # Stamped here rather than taken from the client: the
                        # age of a self-reported figure is the app's record of
                        # when it was told, not the caller's claim about it.
                        "as_of": date.today(),
                        "note": note,
                    }
                )

        if not rows:
            await self.repo.clear_concept(budget_id, concept_key)
            return
        await self.repo.replace_concept(budget_id, concept_key, rows)

    # ── concept catalogue ────────────────────────────────────────────────────

    @staticmethod
    def concepts() -> list[dict[str, Any]]:
        return [asdict(c) for c in CONCEPTS]

    @staticmethod
    def thresholds() -> dict[str, int]:
        return {
            "high_interest_apr": HIGH_INTEREST_APR,
            "retirement_target_rate": RETIREMENT_TARGET_RATE,
            "starter_emergency_fund": STARTER_EMERGENCY_FUND,
            "emergency_fund_months": FULL_EMERGENCY_FUND_MONTHS_LOW,
        }
