"""The wishlist's rules, pure.

Reach, project rollups, cooling-off, review due, still-wanted, the drain
impact — everything the Wishlist tab states about a wish that is not simply
a stored field. No I/O: the service gathers balances and paces, this decides
what they mean, and every rule is a one-line test.

The one figure this never computes is an envelope's balance: that is the
budget page's number, handed in from `BudgetService.get_category_balance`.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from igab.domain.dates import add_months, month_start
from igab.domain.money import quantize_cents

ZERO = Decimal("0")
ONE = Decimal("1")

DEFAULT_COOLING_DAYS = 30
DEFAULT_REVIEW_DAYS = 90
#: "Added a while ago and still wanted" — the line the feature exists for.
STILL_WANTED_MONTHS = 3

ReachState = Literal["now", "months", "no_rate", "unlinked"]
ProjectState = Literal["now", "months", "no_rate", "unlinked", "mixed", "complete", "empty"]


@dataclass(frozen=True)
class WishInput:
    id: UUID
    project_id: UUID | None
    category_id: UUID | None
    cost: Decimal
    priority: int
    created_at: date
    status: str


@dataclass(frozen=True)
class ProjectInput:
    id: UUID
    category_id: UUID | None


@dataclass(frozen=True)
class Funding:
    """An envelope as the budget page reads it, plus how fast it fills."""

    available: Decimal
    monthly_rate: Decimal | None


@dataclass(frozen=True)
class Reach:
    state: ReachState
    months: int | None
    date: date | None
    #: What the wishes ahead of this one in the same envelope still need.
    ahead_cost: Decimal
    #: 0–1, net of the wishes ahead.
    progress: Decimal


@dataclass(frozen=True)
class ProjectSummary:
    item_count: int
    open_count: int
    #: What the open wishes still cost, together.
    total_cost: Decimal
    affordable_now: int
    funded_by: date | None
    state: ProjectState
    complete: bool


def effective_category(wish: WishInput, projects: Mapping[UUID, ProjectInput]) -> UUID | None:
    """A wish's own envelope, else its project's."""
    if wish.category_id is not None:
        return wish.category_id
    if wish.project_id is not None and wish.project_id in projects:
        return projects[wish.project_id].category_id
    return None


def cooling_until_for(created: date, days: int) -> date:
    return created + timedelta(days=max(0, days))


def trailing_average(
    assigned_by_month: Mapping[date, Decimal], month: date, months: int = 3
) -> Decimal:
    """Average assigned over this month and the ones before it, missing
    months counted as nothing — the fallback pace when no target says one."""
    month = month_start(month)
    window = [add_months(month, -i) for i in range(months)]
    total = sum((assigned_by_month.get(m, ZERO) for m in window), ZERO)
    return quantize_cents(total / months)


def _months_to_cover(remaining: Decimal, rate: Decimal) -> int:
    quotient = remaining / rate
    months = int(quotient)
    return months + 1 if quotient > months else months


def reach_for(
    wishes: Iterable[WishInput],
    projects: Mapping[UUID, ProjectInput],
    funding: Mapping[UUID, Funding],
    today: date,
) -> dict[UUID, Reach]:
    """When each open wish can be afforded, from its envelope's real balance.

    One queue per envelope: every open wish drawing on it, whatever project
    it sits in, in priority order — two projects funded from one envelope
    genuinely compete for it, and the wishlist says so rather than promising
    both. A wish ahead in the queue is counted before the one behind it.
    """
    out: dict[UUID, Reach] = {}
    by_envelope: dict[UUID, list[WishInput]] = {}
    for wish in wishes:
        if wish.status != "open":
            continue
        envelope = effective_category(wish, projects)
        if envelope is None or envelope not in funding:
            out[wish.id] = Reach("unlinked", None, None, ZERO, ZERO)
            continue
        by_envelope.setdefault(envelope, []).append(wish)

    for envelope, queue in by_envelope.items():
        fund = funding[envelope]
        cumulative = ZERO
        for wish in sorted(queue, key=lambda w: (w.priority, w.created_at, str(w.id))):
            ahead = cumulative
            cost = quantize_cents(wish.cost)
            cumulative += cost
            covered = fund.available - ahead
            if cost <= ZERO:
                progress = ONE
            else:
                progress = min(ONE, max(ZERO, covered / cost)).quantize(Decimal("0.01"))
            if fund.available >= cumulative:
                out[wish.id] = Reach("now", 0, today, ahead, ONE)
                continue
            rate = fund.monthly_rate
            if rate is None or rate <= ZERO:
                out[wish.id] = Reach("no_rate", None, None, ahead, progress)
                continue
            months = _months_to_cover(cumulative - fund.available, rate)
            out[wish.id] = Reach("months", months, add_months(today, months), ahead, progress)
    return out


def project_summary(
    project_id: UUID, wishes: Iterable[WishInput], reach: Mapping[UUID, Reach]
) -> ProjectSummary:
    members = [w for w in wishes if w.project_id == project_id]
    open_ = [w for w in members if w.status == "open"]
    total = sum((quantize_cents(w.cost) for w in open_), ZERO)
    reaches = [reach[w.id] for w in open_ if w.id in reach]
    now = sum(1 for r in reaches if r.state == "now")

    if not members:
        state: ProjectState = "empty"
    elif not open_:
        state = "complete"
    elif all(r.state == "now" for r in reaches):
        state = "now"
    elif all(r.state in ("now", "months") for r in reaches):
        state = "months"
    elif all(r.state == "unlinked" for r in reaches):
        state = "unlinked"
    elif all(r.state == "no_rate" for r in reaches):
        state = "no_rate"
    else:
        state = "mixed"

    funded_by = None
    if state in ("now", "months") and reaches:
        funded_by = max(r.date for r in reaches if r.date is not None)

    return ProjectSummary(
        item_count=len(members),
        open_count=len(open_),
        total_cost=total,
        affordable_now=now,
        funded_by=funded_by,
        state=state,
        complete=bool(members) and not open_,
    )


def review_due(
    created: date,
    last_affirmed: date | None,
    cooling_until: date | None,
    review_days: int,
    today: date,
) -> bool:
    """Not affirmed for `review_days`. A wish still cooling off is not asked —
    it has not had its chance yet."""
    if cooling_until is not None and cooling_until > today:
        return False
    since = last_affirmed if last_affirmed is not None else created
    return since + timedelta(days=review_days) <= today


def still_wanted(wishes: Iterable[WishInput], today: date) -> tuple[int, int]:
    """(open wishes older than three months, all wishes that old)."""
    cutoff = add_months(today, -STILL_WANTED_MONTHS)
    old = [w for w in wishes if w.created_at <= cutoff]
    return sum(1 for w in old if w.status == "open"), len(old)


def renumber(ids: Iterable[UUID]) -> dict[UUID, int]:
    """Contiguous priorities in the given order — what a reorder writes."""
    return {wish_id: position for position, wish_id in enumerate(ids)}


def drain_impact(amount: Decimal, pace: Decimal | None) -> Decimal | None:
    """How much further away a wish is, in months, after `amount` left its
    envelope at `pace` a month. None when there is no pace to measure by."""
    if pace is None or pace <= ZERO or amount <= ZERO:
        return None
    return (amount / pace).quantize(Decimal("0.01"))
