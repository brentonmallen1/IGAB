"""The wishlist's rules: reach, queues, rollups, cooling, review, still-wanted.

Every figure the Wishlist tab states that is not a stored field comes from
`guide/wishlist.py`, so each rule is pinned here — including the ones that
decide whether to say "you can buy this now" about someone's money.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from igab.domain.dates import add_months
from igab.domain.ordering import renumber
from igab.guide.wishlist import (
    DEFAULT_COOLING_DAYS,
    Funding,
    ProjectInput,
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

TODAY = date(2026, 8, 26)
MONTH = date(2026, 8, 1)


def D(s: str) -> Decimal:
    return Decimal(s)


def wish(
    cost: str,
    *,
    category: UUID | None = None,
    project: UUID | None = None,
    priority: int = 0,
    created: date = TODAY,
    status: str = "open",
    id: UUID | None = None,
) -> WishInput:
    return WishInput(
        id=id or uuid4(),
        project_id=project,
        category_id=category,
        cost=D(cost),
        priority=priority,
        created_at=created,
        status=status,
    )


class TestEffectiveCategory:
    def test_own_category_wins(self):
        own, proj = uuid4(), uuid4()
        p = uuid4()
        w = wish("10", category=own, project=p)
        assert effective_category(w, {p: ProjectInput(p, proj)}) == own

    def test_falls_back_to_the_projects(self):
        proj = uuid4()
        p = uuid4()
        assert effective_category(wish("10", project=p), {p: ProjectInput(p, proj)}) == proj

    def test_unknown_project_is_unlinked(self):
        assert effective_category(wish("10", project=uuid4()), {}) is None


class TestReach:
    def test_unlinked(self):
        r = reach_for([wish("100")], {}, {}, TODAY)
        assert next(iter(r.values())).state == "unlinked"

    def test_linked_but_nothing_assigned_and_no_target_is_no_rate(self):
        cat = uuid4()
        w = wish("100", category=cat)
        r = reach_for([w], {}, {cat: Funding(D("0"), None)}, TODAY)[w.id]
        assert r.state == "no_rate"
        assert r.progress == D("0")

    def test_available_covers_it_now(self):
        cat = uuid4()
        w = wish("100", category=cat)
        r = reach_for([w], {}, {cat: Funding(D("150"), D("50"))}, TODAY)[w.id]
        assert r.state == "now"
        assert r.months == 0
        assert r.progress == D("1")

    def test_exact_available_is_now_not_one_month(self):
        cat = uuid4()
        w = wish("100", category=cat)
        r = reach_for([w], {}, {cat: Funding(D("100"), D("50"))}, TODAY)[w.id]
        assert r.state == "now"

    def test_a_partial_month_rounds_up(self):
        cat = uuid4()
        w = wish("100", category=cat)
        # 100 short at 30 a month: 3.33 → 4 months.
        r = reach_for([w], {}, {cat: Funding(D("0"), D("30"))}, TODAY)[w.id]
        assert r.state == "months"
        assert r.months == 4
        assert r.date == add_months(TODAY, 4)

    def test_exact_division_does_not_round_up(self):
        cat = uuid4()
        w = wish("90", category=cat)
        r = reach_for([w], {}, {cat: Funding(D("0"), D("30"))}, TODAY)[w.id]
        assert r.months == 3

    def test_queue_by_priority_counts_what_is_ahead(self):
        cat = uuid4()
        first = wish("100", category=cat, priority=0)
        second = wish("100", category=cat, priority=1)
        r = reach_for([second, first], {}, {cat: Funding(D("120"), D("40"))}, TODAY)
        assert r[first.id].state == "now"
        assert r[second.id].ahead_cost == D("100")
        # 80 short of 200 at 40 a month.
        assert r[second.id].months == 2
        # Progress is net of the wish ahead: 20 of its own 100.
        assert r[second.id].progress == D("0.20")

    def test_priority_tie_breaks_on_created_then_id(self):
        cat = uuid4()
        older = wish("100", category=cat, created=TODAY - timedelta(days=5))
        newer = wish("100", category=cat, created=TODAY)
        r = reach_for([newer, older], {}, {cat: Funding(D("100"), D("50"))}, TODAY)
        assert r[older.id].state == "now"
        assert r[newer.id].state == "months"
        a = wish("100", category=cat, id=UUID(int=1))
        b = wish("100", category=cat, id=UUID(int=2))
        r = reach_for([b, a], {}, {cat: Funding(D("100"), D("50"))}, TODAY)
        assert r[a.id].state == "now"

    def test_an_overspent_envelope_counts_against_the_queue(self):
        cat = uuid4()
        w = wish("100", category=cat)
        r = reach_for([w], {}, {cat: Funding(D("-50"), D("50"))}, TODAY)[w.id]
        assert r.state == "months"
        assert r.months == 3  # 150 short
        assert r.progress == D("0")

    def test_a_zero_cost_wish_is_now(self):
        cat = uuid4()
        w = wish("0", category=cat)
        r = reach_for([w], {}, {cat: Funding(D("0"), None)}, TODAY)[w.id]
        assert r.state == "now"

    def test_done_wishes_leave_the_queue(self):
        cat = uuid4()
        done = wish("100", category=cat, priority=0, status="done")
        open_ = wish("100", category=cat, priority=1)
        r = reach_for([done, open_], {}, {cat: Funding(D("100"), D("50"))}, TODAY)
        assert done.id not in r
        assert r[open_.id].state == "now"

    def test_a_wish_inherits_its_projects_envelope(self):
        cat, p = uuid4(), uuid4()
        w = wish("100", project=p)
        r = reach_for([w], {p: ProjectInput(p, cat)}, {cat: Funding(D("100"), None)}, TODAY)
        assert r[w.id].state == "now"

    def test_two_projects_on_one_envelope_share_one_queue(self):
        cat, p1, p2 = uuid4(), uuid4(), uuid4()
        a = wish("100", project=p1, priority=0)
        b = wish("100", project=p2, priority=1)
        projects = {p1: ProjectInput(p1, cat), p2: ProjectInput(p2, cat)}
        r = reach_for([a, b], projects, {cat: Funding(D("100"), D("100"))}, TODAY)
        assert r[a.id].state == "now"
        assert r[b.id].months == 1

    def test_an_envelope_deleted_underneath_reads_unlinked(self):
        w = wish("100", category=uuid4())
        assert reach_for([w], {}, {}, TODAY)[w.id].state == "unlinked"


class TestProjectSummary:
    def test_funded_by_is_the_latest_item(self):
        cat, p = uuid4(), uuid4()
        a = wish("100", project=p, priority=0)
        b = wish("100", project=p, priority=1)
        projects = {p: ProjectInput(p, cat)}
        reach = reach_for([a, b], projects, {cat: Funding(D("100"), D("50"))}, TODAY)
        s = project_summary(p, [a, b], reach)
        assert s.state == "months"
        assert s.affordable_now == 1
        assert s.funded_by == add_months(TODAY, 2)
        assert s.total_cost == D("200.00")

    def test_complete_iff_nothing_open(self):
        p = uuid4()
        done = wish("50", project=p, status="done")
        dropped = wish("50", project=p, status="dropped")
        s = project_summary(p, [done, dropped], {})
        assert s.complete and s.state == "complete"
        with_open = project_summary(p, [done, wish("50", project=p)], {})
        assert not with_open.complete

    def test_no_envelope_and_unlinked_items_reads_unlinked(self):
        p = uuid4()
        w = wish("50", project=p)
        s = project_summary(p, [w], reach_for([w], {p: ProjectInput(p, None)}, {}, TODAY))
        assert s.state == "unlinked"
        assert s.funded_by is None

    def test_empty_project(self):
        s = project_summary(uuid4(), [], {})
        assert s.state == "empty" and not s.complete


class TestTrailingAverage:
    def test_missing_months_count_as_zero(self):
        assert trailing_average({MONTH: D("300")}, MONTH) == D("100.00")

    def test_is_cent_quantized(self):
        rows = {MONTH: D("100"), add_months(MONTH, -1): D("0"), add_months(MONTH, -2): D("0")}
        assert trailing_average(rows, MONTH) == D("33.33")

    def test_ignores_months_outside_the_window(self):
        rows = {add_months(MONTH, -3): D("900")}
        assert trailing_average(rows, MONTH) == D("0.00")


class TestCoolingAndReview:
    def test_cooling_default(self):
        assert cooling_until_for(TODAY, DEFAULT_COOLING_DAYS) == TODAY + timedelta(days=30)
        assert cooling_until_for(TODAY, 0) == TODAY

    def test_review_due_at_exactly_n_days(self):
        assert review_due(TODAY - timedelta(days=90), None, None, 90, TODAY)
        assert not review_due(TODAY - timedelta(days=89), None, None, 90, TODAY)

    def test_affirming_resets_the_clock(self):
        assert not review_due(
            TODAY - timedelta(days=400), TODAY - timedelta(days=10), None, 90, TODAY
        )

    def test_a_cooling_wish_is_never_due(self):
        assert not review_due(
            TODAY - timedelta(days=400), None, TODAY + timedelta(days=1), 90, TODAY
        )
        assert review_due(TODAY - timedelta(days=400), None, TODAY, 90, TODAY)


class TestStillWanted:
    def test_counts_only_wishes_older_than_three_months(self):
        old_open = wish("1", created=add_months(TODAY, -3))
        old_done = wish("1", created=add_months(TODAY, -4), status="done")
        recent = wish("1", created=add_months(TODAY, -1))
        assert still_wanted([old_open, old_done, recent], TODAY) == (1, 2)


class TestOrderingAndImpact:
    def test_renumber_is_contiguous_and_order_preserving(self):
        a, b, c = uuid4(), uuid4(), uuid4()
        assert renumber([c, a, b]) == {c: 0, a: 1, b: 2}

    def test_drain_impact(self):
        assert drain_impact(D("100"), D("50")) == D("2.00")
        assert drain_impact(D("100"), D("30")) == D("3.33")
        assert drain_impact(D("100"), None) is None
        assert drain_impact(D("100"), D("0")) is None
        assert drain_impact(D("0"), D("50")) is None
