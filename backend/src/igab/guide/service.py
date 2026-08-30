"""The Guide's one entry point.

`api/v1/guide.py` talks to this and nothing else, which is what keeps the rest
of the package free to change without touching the HTTP layer.
"""

import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Account, Category, Liability
from igab.domain.dates import month_start
from igab.domain.exceptions import InvariantViolation
from igab.guide.bindings import Resolution, resolve_all
from igab.guide.concepts import (
    CONCEPTS,
    CONCEPTS_BY_KEY,
    FULL_EMERGENCY_FUND_MONTHS_HIGH,
    FULL_EMERGENCY_FUND_MONTHS_LOW,
    HIGH_INTEREST_APR,
    RETIREMENT_TARGET_RATE,
    STARTER_EMERGENCY_FUND,
    emergency_fund_target,
    starter_emergency_fund,
)
from igab.guide.detection import (
    Finding,
    GuideDetection,
    budget_service_from,
    category_service_from,
    liability_service_from,
)
from igab.guide.findings import CheckupInputs, evaluate, metrics
from igab.guide.repo import GuideRepository
from igab.guide.scenarios import (
    EmergencyFundPlan,
    LoanCandidate,
    LoanComparison,
    PayoffPlan,
    PayVsSave,
    emergency_fund,
    loan_compare,
    pay_vs_save,
    payoff_plan,
)
from igab.repositories.category_repo import CategoryGroupRepository
from igab.repositories.target_repo import TargetRepository
from igab.services.amortization import CascadeDebt
from igab.services.budget_service import BudgetService
from igab.services.category_service import CategoryArchivePreview
from igab.services.liability_service import LiabilityService
from igab.services.report_service import ReportService
from igab.services.target_service import TargetService

#: Defaults for the two switches on the settings page. Both on: the roadmap is
#: far more useful when it knows the numbers, and every inference it makes is
#: explained and reversible.
DEFAULT_PREFS: dict[str, bool] = {"personalization": True, "checkup": True, "wishlist": True}

PREFS_KEY = "prefs"
STEP_PREFIX = "step:"
#: When the user last pressed "Run health report". The checkup never runs on
#: its own, so this is the only timestamp it has.
CHECKUP_KEY = "checkup"


class GuideService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        budget_service: BudgetService | None = None,
        target_service: TargetService | None = None,
        report_service: ReportService | None = None,
        liability_service: LiabilityService | None = None,
    ) -> None:
        self.session = session
        self.repo = GuideRepository(session)
        # The request path hands in the instances it already built; a test may
        # say `GuideService(session)` and get the same wiring from the session.
        self.budget = budget_service or budget_service_from(session)
        self.liabilities = liability_service or liability_service_from(session)
        self.targets = target_service or TargetService(TargetRepository(session))
        self.reports = report_service or ReportService(session)
        self.categories = category_service_from(session, self.budget)
        self.detection = GuideDetection(session, self.budget, self.liabilities)

    # ── preferences ──────────────────────────────────────────────────────────

    async def preferences(self, budget_id: uuid.UUID) -> dict[str, bool]:
        stored = (await self.repo.state(budget_id)).get(PREFS_KEY, {})
        return {**DEFAULT_PREFS, **{k: bool(v) for k, v in stored.items()}}

    async def preview_wishlist_retire(self, budget_id: uuid.UUID) -> CategoryArchivePreview:
        """What turning the Wishlist off would move, so the switch can say it.

        The same preview archiving a group anywhere else uses, so the figure in
        the dialog and the money the switch actually returns come from one
        place. An empty wishlist previews as empty and the switch just flips.
        """
        groups = CategoryGroupRepository(self.session)
        group = await groups.get_by_system_key(budget_id, "wishlist")
        if group is None:
            return CategoryArchivePreview()
        return await self.categories.preview_archive_group(budget_id, group.id, date.today())

    async def set_preferences(
        self,
        budget_id: uuid.UUID,
        changes: dict[str, bool],
        *,
        release_wishlist_money: bool = False,
    ) -> dict[str, bool]:
        current = await self.preferences(budget_id)
        merged = {**current, **changes}
        # Health findings are built from the same signals, so personalisation
        # off means checkup off. Stored that way rather than only hidden in the
        # UI, so nothing downstream has to remember the rule.
        if not merged.get("personalization", True):
            merged["checkup"] = False
        # The group work goes FIRST, because it can refuse. Storing the
        # preference before it meant a refused wishlist-off still flipped the
        # switch: the settings page read "off" while the group sat in the
        # budget, and the two disagreed until something else refetched.
        if "wishlist" in changes:
            # The Wishlist group follows the switch: off archives it, on brings
            # it back — seeding it the first time.
            #
            # Through the archive routes, never a column write. An archived
            # group takes every envelope under it off the budget
            # (`IN_ARCHIVED_GROUP`), so flipping the flag here used to strand
            # whatever the wish envelopes held: still deducted from Ready to
            # Assign, drawn nowhere, reachable only by turning the switch back
            # on. The hygiene check found it afterwards; nothing prevented it.
            groups = CategoryGroupRepository(self.session)
            if changes["wishlist"]:
                group = await groups.ensure_system_group(budget_id, "wishlist")
                if group.is_archived:
                    await self.categories.unarchive_group(budget_id, group.id)
            else:
                group = await groups.get_by_system_key(budget_id, "wishlist")
                if group is not None and not group.is_archived:
                    await self._retire_wishlist(budget_id, group.id, release_wishlist_money)
        await self.repo.set_state(budget_id, PREFS_KEY, merged)
        return merged

    async def _retire_wishlist(
        self, budget_id: uuid.UUID, group_id: uuid.UUID, release: bool
    ) -> None:
        """Turn the Wishlist off, returning any money in it first.

        The money moves only on an explicit `release`. Refusing by default is
        what makes the confirmation real: a client that has not asked gets the
        figure back as an error and can put it in front of the user, and no
        request that merely says "wishlist: false" can move money on its own.
        The decision is re-measured here rather than trusted from whatever the
        dialog was showing.
        """
        preview = await self.categories.preview_archive_group(budget_id, group_id, date.today())
        if preview.blocked_by_balance and not release:
            names = ", ".join(preview.blocked_by_balance)
            raise InvariantViolation(
                f"Your wishlist still holds {preview.available} in {names}. Turning it off "
                "returns that to Ready to Assign — confirm to continue"
            )
        if preview.blocked_by_balance:
            await self.categories.retire_group(budget_id, group_id)
        else:
            await self.categories.archive_group(budget_id, group_id)

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

        payload: dict[str, Any] = {
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
        if key == "emergency_fund":
            # The roadmap asks about this fund twice — a starter cushion, then
            # the full three to six months — so the signal answers twice.
            # `met`/`target` are the full figure; these are the starter's.
            starter = starter_emergency_fund(essentials.value if essentials else None)
            payload["starter_target"] = starter
            payload["starter_met"] = None if total is None else total >= starter
        return payload

    def _target(self, key: str, essentials: Finding | None) -> Decimal | None:
        match key:
            case "emergency_fund":
                # Three months of real spending once we know it; the flat
                # starter figure until then.
                if essentials and essentials.value:
                    return emergency_fund_target(essentials.value, FULL_EMERGENCY_FUND_MONTHS_LOW)
                return starter_emergency_fund(None)
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

    # ── the checkup ──────────────────────────────────────────────────────────

    async def checkup(self, budget_id: uuid.UUID, *, stamp: bool = False) -> dict[str, Any]:
        """Metrics against their targets, and every finding that fires.

        One computation feeds three surfaces — the Checkup tab, the health
        report, and the step markers on the roadmap — so they cannot disagree.
        With reviews switched off nothing is computed at all: off means off,
        for the household member who finds the whole thing stressful.
        """
        prefs = await self.preferences(budget_id)
        today = date.today()
        state = await self.repo.state(budget_id)
        last_run = state.get(CHECKUP_KEY, {}).get("last_run")
        if not prefs["checkup"]:
            return {
                "enabled": False,
                "as_of": today,
                "last_run": last_run,
                "metrics": [],
                "findings": [],
            }

        signals = await self.signals(budget_id)
        by_key = {c["key"]: c for c in signals["concepts"]}

        plan = await self.reports.plan_vs_reality(budget_id)
        chronic_names = [c["category_name"] for c in plan["categories"] if c["chronic"]]

        # Same composition as the budget month endpoint, so "funded" here is
        # the pill the budget page shows.
        summary = await self.budget.get_budget_summary(budget_id, month_start(today))
        targets = {
            t.category_id: t
            for t in await self.targets.repo.get_by_category_ids(
                [b.category_id for b in summary.category_balances]
            )
        }
        funded = sum(
            1
            for b in summary.category_balances
            if not b.in_system_group
            and (t := targets.get(b.category_id))
            and self.targets.calculate_status(t, b.assigned, b.available, today) != "underfunded"
        )

        essentials = by_key.get("essential_expenses", {})
        inputs = CheckupInputs(
            signals=by_key,
            essentials_monthly=essentials.get("value"),
            chronic_count=plan["chronic_count"],
            chronic_names=chronic_names,
            funded=funded,
            with_targets=len(targets),
            unknown_rate_names=list(by_key.get("high_interest_debt", {}).get("gaps", [])),
            today=today,
            essentials_tracked=bool(essentials.get("tracked", True)),
            essentials_reason=essentials.get("reason", ""),
        )

        if stamp:
            last_run = datetime.now(UTC).isoformat()
            await self.repo.set_state(budget_id, CHECKUP_KEY, {"last_run": last_run})

        return {
            "enabled": True,
            "as_of": today,
            "last_run": last_run,
            "metrics": [asdict(m) for m in metrics(inputs)],
            "findings": [asdict(f) for f in evaluate(inputs)],
        }

    # ── scenario calculators ─────────────────────────────────────────────────
    #
    # Three are pure and pass straight through; the router still comes here
    # so it keeps talking to one object. The fourth reads the roadmap's own
    # figures, which is the point of it.

    @staticmethod
    def payoff_plan(debts: list[CascadeDebt], extra: Decimal, as_of: date) -> PayoffPlan:
        return payoff_plan(debts, extra, as_of)

    @staticmethod
    def pay_vs_save(
        balance: Decimal,
        annual_rate: Decimal,
        minimum_payment: Decimal,
        extra: Decimal,
        savings_apy: Decimal,
        as_of: date,
    ) -> PayVsSave:
        return pay_vs_save(balance, annual_rate, minimum_payment, extra, savings_apy, as_of)

    @staticmethod
    def loan_compare(loans: list[LoanCandidate], as_of: date) -> LoanComparison:
        return loan_compare(loans, as_of)

    async def emergency_fund_plan(
        self, budget_id: uuid.UUID, months: int, monthly_contribution: Decimal
    ) -> EmergencyFundPlan:
        """Size an emergency fund from the signals the roadmap already shows.

        The essentials figure and the emergency-fund figure are the ones on
        the roadmap — including any amount the user declared they hold
        elsewhere, which counts here as it does there and, as everywhere in
        the Guide, nowhere else.
        """
        signals = await self.signals(budget_id)
        by_key = {c["key"]: c for c in signals["concepts"]}
        return emergency_fund(
            current=by_key.get("emergency_fund", {}).get("value"),
            essentials_monthly=by_key.get("essential_expenses", {}).get("value"),
            months=months,
            monthly_contribution=monthly_contribution,
            today=date.today(),
        )

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
                        Category.is_archived == False,  # noqa: E712
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
            "emergency_fund_months_high": FULL_EMERGENCY_FUND_MONTHS_HIGH,
        }
