"""Wire shapes for the Guide's "How money counts" explorer.

Every field is required on the way out: an answer that forgot a leg's class or
a budget term must fail to serialize, not render as "nothing happens".
"""

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from igab.api.v1.schemas.base import ApiModel
from igab.domain.money_moves import (
    AccountShape,
    BudgetTerm,
    CategoryKind,
    Direction,
    LegRole,
    Move,
    MoveKind,
    ReportFamily,
)

Classification = Literal["asset", "liability"]


class AccountShapeIn(ApiModel):
    classification: Classification
    on_budget: bool
    counts_as_savings: bool

    def to_domain(self) -> AccountShape:
        return AccountShape(
            is_liability=self.classification == "liability",
            on_budget=self.on_budget,
            counts_as_savings=self.counts_as_savings,
        )


class MoneyMoveRequest(ApiModel):
    kind: MoveKind
    #: The from-account of a transfer, or the one account of a transaction.
    account: AccountShapeIn
    to_account: AccountShapeIn | None = None
    direction: Direction | None = None
    category: CategoryKind = CategoryKind.NONE
    amount: Decimal = Field(gt=0, le=Decimal("1000000000"))

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> "MoneyMoveRequest":
        if self.kind is MoveKind.TRANSFER and (self.to_account is None or self.direction):
            raise ValueError("a transfer names to_account and no direction")
        if self.kind is MoveKind.TRANSACTION and (self.to_account or self.direction is None):
            raise ValueError("a transaction names a direction and no to_account")
        return self

    def to_domain(self) -> Move:
        return Move(
            kind=self.kind,
            account=self.account.to_domain(),
            to_account=self.to_account.to_domain() if self.to_account else None,
            direction=self.direction,
            category=self.category,
            amount=self.amount,
        )


class MonthMoveRequest(MoneyMoveRequest):
    label: str = Field(min_length=1, max_length=120)


class MoneyMonthRequest(ApiModel):
    moves: list[MonthMoveRequest] = Field(min_length=1, max_length=50)


class LegResponse(ApiModel):
    role: LegRole
    on_budget: bool
    amount: Decimal
    category: CategoryKind
    cls: str
    class_label: str
    reason: str
    reason_text: str
    counted_in: list[ReportFamily]
    planned_spend_by_tag: bool


class BudgetTermResponse(ApiModel):
    term: BudgetTerm
    delta: Decimal


class FiguresResponse(ApiModel):
    income: Decimal
    spending: Decimal
    cost_of_living: Decimal
    savings: Decimal
    debt_principal: Decimal
    savings_rate: float | None
    savings_rate_with_debt: float | None


class MoveExplanationResponse(ApiModel):
    category_role: LegRole | None
    category_applied: bool
    legs: list[LegResponse]
    budget_terms: list[BudgetTermResponse]
    class_totals: dict[str, Decimal]
    figures: FiguresResponse
    net_worth_delta: Decimal
    assumption: str


class MonthRowResponse(ApiModel):
    label: str
    explanation: MoveExplanationResponse


class MoneyMonthResponse(ApiModel):
    rows: list[MonthRowResponse]
    class_totals: dict[str, Decimal]
    figures: FiguresResponse


class RuleResponse(ApiModel):
    position: int
    cls: str
    class_label: str
    reason: str
    reason_text: str
    #: The system tag key the rule reads, or None for a rule about accounts.
    tag_key: str | None
    #: True for the last entry: what a row is when no rule matched.
    is_default: bool


class ReportFamilyResponse(ApiModel):
    key: ReportFamily
    label: str
    classes: list[str]


class ShapeExampleResponse(ApiModel):
    description: str
    explanation: MoveExplanationResponse


class ShapeResponse(ApiModel):
    key: str
    label: str
    classification: Classification
    on_budget: bool
    #: None where the flag changes nothing for this shape.
    counts_as_savings: bool | None
    money_in: ShapeExampleResponse
    money_out: ShapeExampleResponse


class MoneyRulesResponse(ApiModel):
    rules: list[RuleResponse]
    report_families: list[ReportFamilyResponse]
    shapes: list[ShapeResponse]
    #: System tag keys whose outflows plan reports count as spent regardless.
    planned_spend_tag_keys: list[str]
