"""Guide endpoints.

Thin by design: parse, authorise, delegate to GuideService, return. Everything
that decides anything lives in igab.guide, which nothing else imports.
"""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from igab.api.route import CommitRoute
from igab.api.v1.schemas.guide import (
    BindingUpdate,
    CandidatesResponse,
    CheckupResponse,
    EmergencyFundRequest,
    EmergencyFundResponse,
    GuideOverview,
    LoanCompareRequest,
    LoanCompareResponse,
    PayoffPlanRequest,
    PayoffPlanResponse,
    PayVsSaveRequest,
    PayVsSaveResponse,
    PreferencesResponse,
    PreferencesUpdate,
    SignalsResponse,
    StepUpdate,
    WishlistRetirePreview,
)
from igab.api.v1.schemas.money_moves import (
    BudgetTermResponse,
    FiguresResponse,
    LegResponse,
    MoneyMonthRequest,
    MoneyMonthResponse,
    MoneyMoveRequest,
    MoneyRulesResponse,
    MonthRowResponse,
    MoveExplanationResponse,
    ReportFamilyResponse,
    RuleResponse,
    ShapeExampleResponse,
    ShapeResponse,
)
from igab.dependencies import (
    BudgetAccess,
    CurrentUser,
    get_guide_service,
    get_money_moves_service,
)
from igab.domain.activity_class import (
    CLASS_LABEL,
    PLANNED_SPEND_TAG_KEYS,
    REASON_TEXT,
    rule_ladder,
)
from igab.domain.exceptions import InvariantViolation
from igab.domain.money_moves import (
    ASSUMPTION,
    REPORT_FAMILY_CLASSES,
    REPORT_FAMILY_LABEL,
    Figures,
    MoveExplanation,
    figures,
)
from igab.guide.concepts import CONCEPT_KEYS
from igab.guide.scenarios import LoanCandidate
from igab.guide.service import GuideService
from igab.services.amortization import CascadeDebt
from igab.services.money_moves_service import MoneyMovesService
from igab.utils.clock import today_utc

router = APIRouter(route_class=CommitRoute)

GuideServiceDep = Annotated[GuideService, Depends(get_guide_service)]
MoneyMovesDep = Annotated[MoneyMovesService, Depends(get_money_moves_service)]


def _known(concept_key: str) -> str:
    if concept_key not in CONCEPT_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown concept '{concept_key}'"
        )
    return concept_key


@router.get("/{budget_id}/guide", response_model=GuideOverview)
async def guide_overview(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> GuideOverview:
    return GuideOverview(
        concepts=GuideService.concepts(),
        thresholds=GuideService.thresholds(),
        preferences=PreferencesResponse(**await service.preferences(budget_id)),
        progress=await service.progress(budget_id),
    )


@router.get("/{budget_id}/guide/signals", response_model=SignalsResponse)
async def guide_signals(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> SignalsResponse:
    return SignalsResponse(**await service.signals(budget_id))


@router.get("/{budget_id}/guide/candidates/{concept_key}", response_model=CandidatesResponse)
async def guide_candidates(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    concept_key: str,
) -> CandidatesResponse:
    key = _known(concept_key)
    return CandidatesResponse(concept_key=key, options=await service.candidates(budget_id, key))


@router.put("/{budget_id}/guide/bindings/{concept_key}", status_code=status.HTTP_204_NO_CONTENT)
async def set_guide_binding(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    concept_key: str,
    payload: BindingUpdate,
) -> None:
    key = _known(concept_key)
    await service.set_binding(
        budget_id,
        key,
        mode=payload.mode,
        entity_ids=payload.entity_ids,
        answer=payload.answer,
        external=payload.external,
        external_amount=payload.external_amount,
        note=payload.note,
    )


@router.get("/{budget_id}/guide/preferences", response_model=PreferencesResponse)
async def guide_preferences(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> PreferencesResponse:
    return PreferencesResponse(**await service.preferences(budget_id))


@router.put("/{budget_id}/guide/preferences", response_model=PreferencesResponse)
async def set_guide_preferences(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: PreferencesUpdate,
) -> PreferencesResponse:
    changes = payload.model_dump(exclude_none=True)
    release = bool(changes.pop("release_wishlist_money", False))
    try:
        return PreferencesResponse(
            **await service.set_preferences(budget_id, changes, release_wishlist_money=release)
        )
    except InvariantViolation as e:
        # Turning the Wishlist off with money in it: the message carries the
        # figure, so the dialog can state it rather than guessing.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/{budget_id}/guide/wishlist/retire-preview", response_model=WishlistRetirePreview)
async def wishlist_retire_preview(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> WishlistRetirePreview:
    """What turning the Wishlist off would move, before the switch is flipped."""
    preview = await service.preview_wishlist_retire(budget_id)
    return WishlistRetirePreview(
        envelopes=preview.blocked_by_balance,
        available=preview.available,
        is_empty=not preview.blocked_by_balance,
    )


@router.put("/{budget_id}/guide/progress/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_guide_step(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    stage_id: str,
    payload: StepUpdate,
) -> None:
    await service.set_step(budget_id, stage_id, payload.state)


@router.get("/{budget_id}/guide/checkup", response_model=CheckupResponse)
async def guide_checkup(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> CheckupResponse:
    return CheckupResponse(**await service.checkup(budget_id))


@router.post("/{budget_id}/guide/checkup/run", response_model=CheckupResponse)
async def run_health_report(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
) -> CheckupResponse:
    """The health report, run because the user pressed the button.

    Same payload as the GET, plus a stamp recording that they looked. Refused
    rather than quietly empty when reviews are off — a run that does nothing
    must not report success.
    """
    result = await service.checkup(budget_id, stamp=True)
    if not result["enabled"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Financial health reviews are switched off for this budget",
        )
    return CheckupResponse(**result)


# ── scenario calculators ─────────────────────────────────────────────────────
# POST because the inputs are a document, not a filter; nothing is stored.


@router.post("/{budget_id}/guide/scenarios/payoff-plan", response_model=PayoffPlanResponse)
async def scenario_payoff_plan(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: PayoffPlanRequest,
) -> PayoffPlanResponse:
    debts = [CascadeDebt(**d.model_dump()) for d in payload.debts]
    return PayoffPlanResponse.model_validate(
        asdict(service.payoff_plan(debts, payload.extra, today_utc()))
    )


@router.post("/{budget_id}/guide/scenarios/pay-vs-save", response_model=PayVsSaveResponse)
async def scenario_pay_vs_save(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: PayVsSaveRequest,
) -> PayVsSaveResponse:
    return PayVsSaveResponse.model_validate(
        asdict(
            service.pay_vs_save(
                payload.balance,
                payload.annual_rate,
                payload.minimum_payment,
                payload.extra,
                payload.savings_apy,
                today_utc(),
            )
        )
    )


@router.post("/{budget_id}/guide/scenarios/loan-compare", response_model=LoanCompareResponse)
async def scenario_loan_compare(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: LoanCompareRequest,
) -> LoanCompareResponse:
    loans = [LoanCandidate(**loan.model_dump()) for loan in payload.loans]
    return LoanCompareResponse.model_validate(asdict(service.loan_compare(loans, today_utc())))


@router.post("/{budget_id}/guide/scenarios/emergency-fund", response_model=EmergencyFundResponse)
async def scenario_emergency_fund(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: GuideServiceDep,
    payload: EmergencyFundRequest,
) -> EmergencyFundResponse:
    plan = await service.emergency_fund_plan(
        budget_id, payload.months, payload.monthly_contribution
    )
    return EmergencyFundResponse.model_validate(asdict(plan))


# ── how money counts ─────────────────────────────────────────────────────────
# Explanations of the classifier, answered by the classifier: see
# domain/money_moves.py. Budget-independent, but budget-scoped like every
# Guide route so access is checked the same way.


def _figures(f: Figures) -> FiguresResponse:
    return FiguresResponse.model_validate(asdict(f))


def _explanation(e: MoveExplanation) -> MoveExplanationResponse:
    return MoveExplanationResponse(
        category_role=e.category_role,
        category_applied=e.category_applied,
        legs=[
            LegResponse(
                role=leg.role,
                on_budget=leg.on_budget,
                amount=leg.amount,
                category=leg.category,
                cls=leg.cls.value,
                class_label=CLASS_LABEL[leg.cls],
                reason=leg.reason.value,
                reason_text=REASON_TEXT[leg.reason],
                counted_in=leg.counted_in,
                planned_spend_by_tag=leg.planned_spend_by_tag,
            )
            for leg in e.legs
        ],
        budget_terms=[
            BudgetTermResponse(term=term, delta=delta) for term, delta in e.budget_terms.items()
        ],
        class_totals=e.class_totals,
        figures=_figures(figures(e.class_totals)),
        net_worth_delta=e.net_worth_delta,
        assumption=ASSUMPTION,
    )


@router.get("/{budget_id}/guide/money-rules", response_model=MoneyRulesResponse)
async def money_rules(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: MoneyMovesDep,
) -> MoneyRulesResponse:
    """The classifier's rule ladder in order, and what each account shape does."""
    ladder = rule_ladder()
    return MoneyRulesResponse(
        rules=[
            RuleResponse(
                position=i + 1,
                cls=rule.cls.value,
                class_label=CLASS_LABEL[rule.cls],
                reason=rule.reason.value,
                reason_text=REASON_TEXT[rule.reason],
                tag_key=rule.tag_key,
                is_default=i == len(ladder) - 1,
            )
            for i, rule in enumerate(ladder)
        ],
        report_families=[
            ReportFamilyResponse(
                key=family, label=REPORT_FAMILY_LABEL[family], classes=[c.value for c in classes]
            )
            for family, classes in REPORT_FAMILY_CLASSES.items()
        ],
        shapes=[
            ShapeResponse(
                key=s.shape.key,
                label=s.shape.label,
                classification="liability" if s.shape.is_liability else "asset",
                on_budget=s.shape.on_budget,
                counts_as_savings=s.shape.counts_as_savings,
                money_in=ShapeExampleResponse(
                    description=s.shape.money_in.description,
                    explanation=_explanation(s.money_in),
                ),
                money_out=ShapeExampleResponse(
                    description=s.shape.money_out.description,
                    explanation=_explanation(s.money_out),
                ),
            )
            for s in await service.shapes()
        ],
        planned_spend_tag_keys=list(PLANNED_SPEND_TAG_KEYS),
    )


@router.post("/{budget_id}/guide/money-moves/explain", response_model=MoveExplanationResponse)
async def explain_money_move(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: MoneyMovesDep,
    payload: MoneyMoveRequest,
) -> MoveExplanationResponse:
    """What one hypothetical move counts as. Nothing is written."""
    return _explanation(await service.explain(payload.to_domain()))


@router.post("/{budget_id}/guide/money-moves/month", response_model=MoneyMonthResponse)
async def explain_money_month(
    budget_id: BudgetAccess,
    current_user: CurrentUser,
    service: MoneyMovesDep,
    payload: MoneyMonthRequest,
) -> MoneyMonthResponse:
    """A month of example moves: each one's classes, the totals, both rates."""
    month = await service.month([m.to_domain() for m in payload.moves])
    return MoneyMonthResponse(
        rows=[
            MonthRowResponse(label=m.label, explanation=_explanation(e))
            for m, e in zip(payload.moves, month.moves, strict=True)
        ],
        class_totals=month.class_totals,
        figures=_figures(month.figures),
    )
