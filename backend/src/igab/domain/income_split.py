"""Where take-home pay went: needs, wants, savings & debt, and what was left.

The Income Split report sets a household's own split beside the 50/30/20 rule
of thumb. The rule itself — the 50, the 30, the 20 — is the page's to draw
(`frontend/src/components/reports/incomeSplit.ts`); no backend path decides
anything by it. What lives here is the partition: every dollar that came in,
placed in exactly one bucket, so the buckets add back up to income to the
cent and no row is counted twice.

Which ROWS belong to which bucket is SQL (`domain.activity_class`:
ESSENTIAL_ROW, COMMITTED_ROW, DISCRETIONARY_ROW, NON_ESSENTIAL_DEBT_OUTFLOW);
saved is the Savings Rate's own figure (`report_basics.savings_contributors`).
This module takes those, spreads yearly bills when the budget asks, and adds
up — pure, so every branch is a one-line test.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from igab.domain.dates import add_months, month_end
from igab.domain.money import quantize_cents

ZERO = Decimal("0")

#: The row buckets the SQL sorts spending and debt into.
NEEDS = "needs"
COMMITTED = "committed"
CHOSEN = "chosen"
UNCATEGORIZED = "uncategorized"
DEBT = "debt"

#: Why a row is where it is — the "Counted because" chip. Keys, not words: the
#: page holds the words (incomeSplit.ts), and the keys are what tests pin.
REASON_ESSENTIAL = "essential"
REASON_ESSENTIAL_DEBT = "essential_debt"
REASON_COST_OF_LIVING = "cost_of_living"
REASON_UNTAGGED = "untagged"
REASON_DEBT_NOT_ESSENTIAL = "debt_not_essential"
REASON_DEBT_NO_CATEGORY = "debt_no_category"
REASON_SAVED = "saved"

#: Months a Long-term expense's bills are spread over — the Essentials
#: figure's own span (`guide.concepts.SPREAD_MONTHS`), restated as a constant
#: of this module's arithmetic and pinned equal to it by a test.
SPREAD_MONTHS = 12

#: An average month, for a range that is not whole months. A whole-month range
#: never reads it: its months are counted, not estimated.
DAYS_PER_MONTH = Decimal("365.2425") / 12


@dataclass(frozen=True)
class CategoryRow:
    """One category's rows in one bucket over the window, as the SQL grouped
    them. `outflow` is a magnitude — spending stored negative, flipped — and
    stays signed: a category whose refunds beat its spending is negative."""

    bucket: str
    category_id: uuid.UUID | None
    name: str | None
    group_name: str | None
    is_debt: bool
    sinking: bool
    outflow: Decimal
    count: int
    #: The debt this row pays, when one is on file; and the account it was
    #: paid to, to name a payment that has no category.
    liability_id: uuid.UUID | None = None
    counterpart_name: str | None = None


@dataclass(frozen=True)
class SavedPart:
    """One of the Savings Rate's savings contributors over the window."""

    name: str
    reason_label: str
    total: Decimal


@dataclass(frozen=True)
class Minimum:
    """A debt's minimum payment as of today, and its name."""

    name: str
    monthly: Decimal | None


@dataclass(frozen=True)
class SplitLine:
    category_id: uuid.UUID | None
    name: str
    group_name: str | None
    reason: str
    #: What the line counts — spread when `spread` is set.
    total: Decimal
    count: int
    #: The yearly bill spread over 12 months, with what was actually paid in
    #: the window beside it, so the page can say both.
    spread: bool = False
    as_paid: Decimal | None = None
    #: For a debt payment with a minimum on file: the minimum per month, and
    #: how much of this window's payments went above it.
    minimum: Decimal | None = None
    above_minimum: Decimal | None = None
    #: A debt payment whose debt has no usable minimum on file.
    minimum_unknown: bool = False


@dataclass
class IncomeSplit:
    income: Decimal
    needs: list[SplitLine] = field(default_factory=list)
    committed: list[SplitLine] = field(default_factory=list)
    chosen: list[SplitLine] = field(default_factory=list)
    saved: list[SplitLine] = field(default_factory=list)
    debt: list[SplitLine] = field(default_factory=list)
    uncategorized: Decimal = ZERO
    uncategorized_count: int = 0

    @property
    def needs_total(self) -> Decimal:
        return _sum(self.needs)

    @property
    def wants_total(self) -> Decimal:
        return _sum(self.committed) + _sum(self.chosen)

    @property
    def savings_debt_total(self) -> Decimal:
        return _sum(self.saved) + _sum(self.debt)

    @property
    def left_over(self) -> Decimal:
        """What came in and was neither spent nor saved — still in envelopes
        or Ready to Assign. Negative when outflows ran past income. By
        construction, so the five buckets always add back up to income."""
        return (
            self.income
            - self.needs_total
            - self.wants_total
            - self.savings_debt_total
            - self.uncategorized
        )

    @property
    def above_minimum(self) -> Decimal:
        """Essential debt payments above their minimums — what the rule's own
        reading moves from Needs to Savings & debt."""
        return sum((line.above_minimum or ZERO for line in self.needs), ZERO)


def _sum(lines: Sequence[SplitLine]) -> Decimal:
    return sum((line.total for line in lines), ZERO)


def months_covered(start: date, end: date) -> tuple[Decimal, bool]:
    """How many months [start, end] spans, and whether that is a whole number
    of calendar months.

    Whole months are counted (Jul 1 – Sep 30 is 3). Anything else is days ÷ an
    average month — a custom range, or a month in progress — and the page says
    totals rather than "per month" for it. An empty range is zero months.
    """
    if end < start:
        return ZERO, False
    whole = start.day == 1 and end == month_end(end)
    if whole:
        months = (end.year - start.year) * 12 + (end.month - start.month) + 1
        return Decimal(months), True
    days = Decimal((end - start).days + 1)
    return days / DAYS_PER_MONTH, False


def spread_year(end: date) -> tuple[date, date]:
    """The twelve months a window ending at `end` spreads its yearly bills
    over: the month `end` falls in and the eleven before it — the same twelve
    `guide.concepts.spread_average` reads for a window ending on a month's
    last day."""
    first = add_months(end.replace(day=1), -(SPREAD_MONTHS - 1))
    return first, end


def _reason(row: CategoryRow) -> str:
    if row.bucket == NEEDS:
        return REASON_ESSENTIAL_DEBT if row.is_debt else REASON_ESSENTIAL
    if row.bucket == COMMITTED:
        return REASON_COST_OF_LIVING
    if row.bucket == DEBT:
        return REASON_DEBT_NO_CATEGORY if row.category_id is None else REASON_DEBT_NOT_ESSENTIAL
    return REASON_UNTAGGED


def partition(
    *,
    income: Decimal,
    rows: Sequence[CategoryRow],
    saved: Sequence[SavedPart],
    months: Decimal,
    spread_on: bool,
    year_sinking: Mapping[tuple[str, uuid.UUID | None], Decimal] | None = None,
    minimums: Mapping[uuid.UUID, Minimum] | None = None,
) -> IncomeSplit:
    """Every row in its bucket, yearly bills spread when `spread_on`.

    **Spreading.** A row in a Long-term expense category counts a twelfth of
    that category's last twelve months for each month the window covers
    (`year_sinking`, keyed by (bucket, category)), not what happened to be
    paid inside the window: a $1,752 premium is $146 a month whichever month
    it landed in. For the last three complete months this is exactly the
    Essentials headline's spread figure. Off, every row counts as paid.

    **Minimums.** An Essential debt payment whose debt has a minimum on file
    says how much of the window's payments went above it — the rule's own
    reading counts only the minimum as a need. A minimum is today's figure;
    for a debt whose minimum is a share of its balance it is not the one that
    applied months ago, and the page labels it "minimum today".
    """
    year_sinking = year_sinking or {}
    minimums = minimums or {}
    split = IncomeSplit(income=quantize_cents(income))
    for row in rows:
        if row.bucket == UNCATEGORIZED:
            split.uncategorized += quantize_cents(row.outflow)
            split.uncategorized_count += row.count
            continue
        as_paid = quantize_cents(row.outflow)
        spread = spread_on and row.sinking and months > 0
        total = (
            quantize_cents(
                year_sinking.get((row.bucket, row.category_id), ZERO) / SPREAD_MONTHS * months
            )
            if spread
            else as_paid
        )
        minimum, above, unknown = _against_minimum(row, total, months, minimums)
        line = SplitLine(
            category_id=row.category_id,
            name=row.name or row.counterpart_name or "",
            group_name=row.group_name,
            reason=_reason(row),
            total=total,
            count=row.count,
            spread=spread,
            as_paid=as_paid if spread else None,
            minimum=minimum,
            above_minimum=above,
            minimum_unknown=unknown,
        )
        getattr(split, _LIST[row.bucket]).append(line)
    for part in saved:
        split.saved.append(
            SplitLine(
                category_id=None,
                name=part.name,
                group_name=None,
                reason=REASON_SAVED,
                total=quantize_cents(part.total),
                count=0,
            )
        )
    for lines in (split.needs, split.committed, split.chosen, split.saved, split.debt):
        lines.sort(key=lambda line: (-line.total, line.name))
    return split


_LIST = {NEEDS: "needs", COMMITTED: "committed", CHOSEN: "chosen", DEBT: "debt"}


def _against_minimum(
    row: CategoryRow, total: Decimal, months: Decimal, minimums: Mapping[uuid.UUID, Minimum]
) -> tuple[Decimal | None, Decimal | None, bool]:
    """(minimum per month, paid above it over the window, minimum unknown)."""
    if not row.is_debt:
        return None, None, False
    found = minimums.get(row.liability_id) if row.liability_id is not None else None
    if found is None or found.monthly is None or months <= 0:
        return None, None, True
    owed = found.monthly * months
    return found.monthly, quantize_cents(max(ZERO, total - owed)), False


def strict_reading(split: IncomeSplit) -> tuple[Decimal, Decimal]:
    """(Needs, Savings & debt) as the rule itself reads them: only a debt's
    minimum is a need, and what was paid above it is debt repaid."""
    moved = split.above_minimum
    return split.needs_total - moved, split.savings_debt_total + moved


def window_end_for(end: date, today: date) -> date:
    """A window reads through the reader's today at the latest — a future-dated
    row is in no report's figures, as the Savings Rate reads its window."""
    return min(end, today)


def clamp_to_history(start: date, earliest: date | None) -> tuple[date, bool]:
    """(start, clamped?): a window never reaches before the month of the
    budget's first transaction. A month before the history is not a month of
    zero spending; it is a month nobody recorded, and dividing by it
    under-reads every figure. Cut at the month, as the Essentials window is
    (`domain.dates.complete_month_window`), so a whole-month range stays one."""
    if earliest is None:
        return start, False
    first = earliest.replace(day=1)
    if start < first:
        return first, True
    return start, False
