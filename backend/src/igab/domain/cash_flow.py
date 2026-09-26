"""The Cash Flow diagram: where the money came from and where it went.

Pure: rows (or assignments) in, the diagram's nodes and links out, so every
netting and balancing rule is a one-line test. `ReportService.cash_flow_sankey`
reads the rows; this decides what they draw.

The shape, in both modes: sources on the left flow into one hub ("Budget"),
and the hub flows out to category groups, each to its categories. **The two
sides always balance** — a "Left over" sink or a "Shortfall" source makes up
the difference — so every node is exactly as wide as what went through it.

Spent mode is **net**, the rule Income vs Expenses reads: a category's refunds
come off its spending, money drawn back out of savings comes off what was
moved there, and new borrowing comes off what was repaid. A line that nets to
an inflow is drawn on the left instead ("Refunds", "From savings",
"Borrowed"). So the hub's Left over / Shortfall is Income vs Expenses' `net`
for the same window, to the cent. It used to be gross: refunds, withdrawals
and new borrowing were all dropped, and the client drew one "Income" node as
wide as the outflows — twice the month's real income in one window, beside a
Net that missed Income vs Expenses' by everything the gross sums left out.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from igab.domain.activity_class import ActivityClass
from igab.domain.spending import UNCATEGORIZED as UNCATEGORIZED_NAME
from igab.domain.spending import spent

HUB = "__budget__"
#: Income sources drawn by name; the rest are one "Other income" node, so the
#: sources still add up to the income total — the export's TOTAL row read
#: more than its fifteen income links did.
INCOME_SOURCES_SHOWN = 15
#: Payees drawn by name under a category; the rest are one "Other payees".
PAYEES_SHOWN = 10
#: Categories named in a group's tooltip.
TOOLTIP_CATEGORIES = 10

#: Saving and paying down debt leave the budget but are not spending, so they
#: get their own trunk off the hub instead of sitting inside an expense group
#: where they would read as consumption. The real categories still hang
#: beneath. "To savings accounts", not "Savings": this is money MOVED — a
#: kept-here envelope's held balance never left the budget, and Savings Rate's
#: "Saved" adds it (`test_sankey_spent_mode_is_money_moved`).
CLASS_BRANCH: dict[str, tuple[str, str]] = {
    ActivityClass.SAVINGS.value: ("__savings__", "To savings accounts"),
    ActivityClass.DEBT_PRINCIPAL.value: ("__debt_principal__", "Debt payments"),
}
#: What spent mode reads besides spending: income on the left, and the two
#: class trunks on the right — the classes Income vs Expenses' `net`
#: subtracts beside spending (`money_moves.flows`). Spending itself is not
#: here: it is `ReportService._spending_rows`, the rows every spending report
#: counts. No other class reaches the hub. A card credit nobody filed
#: (TRANSFER_INTERNAL, `activity_class` rule 10) was read with everything
#: else and drawn as "Other money in", so Net ran over Income vs Expenses' by
#: every unfiled refund on a card.
HUB_CLASSES: tuple[str, ...] = (ActivityClass.INCOME.value, *CLASS_BRANCH)
UNCATEGORIZED = ("__uncategorized__", UNCATEGORIZED_NAME)
#: An income source that nets negative in the window (a clawed-back pay, a
#: negative adjustment filed to Ready to Assign): money that left, on the right.
INCOME_REVERSED = ("__income_reversed__", "Income reversed")

#: What a line that nets to an INFLOW is called on the left, by what it is.
#: From the budget's point of view — where did this money come from.
INFLOW_LABELS: dict[str, str] = {
    "refunds": "Refunds",
    "savings": "From savings",
    "debt_principal": "Borrowed",
    "investment_return": "Investment gains",
    "other": "Other money in",
}
LEFT_OVER = ("__left_over__", "Left over")
SHORTFALL = ("__shortfall__", "Shortfall")


def _inflow_kind(group_id: str, classes: set[str]) -> str:
    if group_id == CLASS_BRANCH[ActivityClass.SAVINGS.value][0]:
        return "savings"
    if group_id == CLASS_BRANCH[ActivityClass.DEBT_PRINCIPAL.value][0]:
        return "debt_principal"
    if classes == {ActivityClass.SPENDING.value}:
        return "refunds"
    if ActivityClass.INVESTMENT_RETURN.value in classes:
        return "investment_return"
    return "other"


@dataclass(frozen=True)
class FlowRow:
    """One leaf row, as the diagram needs it."""

    amount: Decimal
    activity_class: str
    is_income: bool
    payee_id: str | None
    payee_name: str | None
    category_id: str | None
    category_name: str | None
    group_id: str | None
    group_name: str | None


@dataclass
class _Line:
    """A (group, category) slot, netted."""

    group_name: str
    name: str
    entity_id: str | None
    net: Decimal = Decimal(0)
    classes: set[str] = field(default_factory=set)
    payees: dict[str, Decimal] = field(default_factory=dict)


class _Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.links: list[dict] = []
        self._ids: set[str] = set()

    def node(self, nid: str, name: str, ntype: str, **extra) -> str:
        if nid not in self._ids:
            self._ids.add(nid)
            self.nodes.append(
                {
                    "id": nid,
                    "name": name,
                    "type": ntype,
                    "entity_id": None,
                    "activity_classes": None,
                }
                | extra
            )
        return nid

    def link(self, source: str, target: str, value: Decimal) -> None:
        self.links.append({"source": source, "target": target, "value": value})


def _ranked(items: dict[str, Decimal], shown: int) -> tuple[list[tuple[str, Decimal]], Decimal]:
    """The `shown` largest, and what the rest add up to."""
    ranked = sorted(items.items(), key=lambda kv: -kv[1])
    return ranked[:shown], sum((v for _, v in ranked[shown:]), Decimal(0))


def _draw_right(
    d: _Diagram,
    lines: dict[tuple[str, str], _Line],
    payee_names: dict[str, str],
    group_names: dict[str, str],
    inflow_label: Callable[[str, set[str]], str],
) -> tuple[Decimal, dict[str, Decimal], dict, dict, dict]:
    """Groups and categories off the hub; returns (drawn outflow, inflows by
    label, category_payees, group_categories, category_returns)."""
    outflow_by_group: dict[str, Decimal] = {}
    inflows: dict[str, Decimal] = {}
    for (gid, _cid), line in lines.items():
        out = -line.net
        if out > 0:
            outflow_by_group[gid] = outflow_by_group.get(gid, Decimal(0)) + out
        elif out < 0:
            label = inflow_label(gid, line.classes)
            inflows[label] = inflows.get(label, Decimal(0)) - out

    category_payees: dict[str, list[dict]] = {}
    group_categories: dict[str, list[dict]] = {}
    category_returns: dict[str, dict] = {}
    for gid, total in sorted(outflow_by_group.items(), key=lambda kv: -kv[1]):
        group_node = d.node(f"g_{gid}", group_names[gid], "category_group")
        d.link(HUB, group_node, total)
        in_group = {cid: line for (g, cid), line in lines.items() if g == gid and line.net < 0}
        shown, _ = _ranked({cid: -line.net for cid, line in in_group.items()}, TOOLTIP_CATEGORIES)
        group_categories[group_node] = [
            {"name": in_group[cid].name, "total": value} for cid, value in shown
        ]
        for cid, line in sorted(in_group.items(), key=lambda kv: kv[1].net):
            # Keyed by (group, category): one category can sit under its own
            # group and a class trunk at once. The composite is a display key;
            # `entity_id` is what a drill needs.
            node = d.node(
                f"c_{gid}_{cid}",
                line.name,
                "category",
                entity_id=line.entity_id,
                activity_classes=sorted(line.classes) or None,
            )
            d.link(group_node, node, -line.net)
            # Payees net too. Those that net to an outflow are drawn; those
            # that net to an inflow (a return with nothing bought this window)
            # are what makes the drawn payees wider than the category, and
            # that difference is served beside them so the level balances.
            bought = {p: -v for p, v in line.payees.items() if v < 0}
            top, rest = _ranked(bought, PAYEES_SHOWN)
            listed = [{"name": payee_names[p], "total": v} for p, v in top]
            if rest > 0:
                listed.append({"name": "Other payees", "total": rest})
            category_payees[node] = listed
            returned = sum(bought.values(), Decimal(0)) + line.net
            if returned > 0:
                category_returns[node] = {
                    "name": inflow_label(gid, line.classes),
                    "total": returned,
                }
    return (
        sum(outflow_by_group.values(), Decimal(0)),
        inflows,
        category_payees,
        group_categories,
        category_returns,
    )


def _balance(d: _Diagram, money_in: Decimal, money_out: Decimal, sink: tuple[str, str]) -> None:
    """Make the two sides equal: what came in and was not drawn out is a sink
    on the right; what went out beyond what came in is a Shortfall source."""
    if money_in > money_out:
        d.link(HUB, d.node(f"g_{sink[0]}", sink[1], "left_over"), money_in - money_out)
    elif money_out > money_in:
        d.link(d.node(SHORTFALL[0], SHORTFALL[1], "shortfall"), HUB, money_out - money_in)


def _slot(r: FlowRow) -> tuple[str, str, str, str]:
    """(group id, group name, category id, category name) a row draws under.
    Uncategorized rows get their own pseudo group, so every row has a line."""
    branch = CLASS_BRANCH.get(r.activity_class)
    if r.category_id:
        cname = r.category_name or r.category_id
        if branch:
            return (*branch, r.category_id, cname)
        return (
            r.group_id or UNCATEGORIZED[0],
            r.group_name or UNCATEGORIZED[1],
            r.category_id,
            cname,
        )
    if branch:
        return (*branch, *branch)
    return (*UNCATEGORIZED, *UNCATEGORIZED)


@dataclass
class _Tally:
    """Rows netted: income by source, everything else by (group, category)."""

    income: dict[str, Decimal] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    lines: dict[tuple[str, str], _Line] = field(default_factory=dict)
    group_names: dict[str, str] = field(default_factory=dict)

    def line(self, gid: str, gname: str, cid: str, cname: str) -> _Line:
        self.group_names[gid] = gname
        entity = None if cid.startswith("__") else cid
        return self.lines.setdefault((gid, cid), _Line(gname, cname, entity))

    def add(self, r: FlowRow) -> None:
        if r.is_income:
            pname = r.payee_name or "Unknown Income"
            key = f"inc_{r.payee_id or pname}"
            self.income[key] = self.income.get(key, Decimal(0)) + r.amount
            self.names[key] = pname
            return
        pname = r.payee_name or "Unknown"
        self._book(self.line(*_slot(r)), r.payee_id or f"__payee_{pname}__", pname, r)

    def _book(self, line: _Line, pkey: str, pname: str, r: FlowRow) -> None:
        line.net += r.amount
        line.classes.add(r.activity_class)
        line.payees[pkey] = line.payees.get(pkey, Decimal(0)) + r.amount
        self.names[pkey] = pname

    def reverse_negative_income(self) -> None:
        """A source that nets to an outflow is money that left: on the right."""
        for key, value in self.income.items():
            if value < 0:
                line = self.line(*INCOME_REVERSED, *INCOME_REVERSED)
                line.net += value
                line.classes.add(ActivityClass.INCOME.value)
                line.payees[key] = line.payees.get(key, Decimal(0)) + value


def spent_diagram(rows: Sequence[FlowRow], spending_classes: Collection[str]) -> dict:
    """The spent-mode diagram, net, from leaf rows (no split parents, no
    starting balances): the spending rows every spending report counts, whose
    classes are `spending_classes` (`counted_classes`, which widens on an
    account selection), and the `HUB_CLASSES` rows. `net` is money in less
    money out — Income vs Expenses' `net` over the same rows."""
    d = _Diagram()
    d.node(HUB, "Budget", "budget")
    tally = _Tally()
    for r in rows:
        tally.add(r)
    tally.reverse_negative_income()
    total_income = sum(tally.income.values(), Decimal(0))

    # Sources: the served income, largest first, then what is not income.
    earned = {k: v for k, v in tally.income.items() if v > 0}
    top, rest = _ranked(earned, INCOME_SOURCES_SHOWN)
    for key, value in top:
        d.link(d.node(key, tally.names[key], "income_payee"), HUB, value)
    if rest > 0:
        d.link(d.node("inc___other__", "Other income", "income_payee"), HUB, rest)

    kind_of: dict[str, str] = {}

    def inflow_label(gid: str, classes: set[str]) -> str:
        kind = _inflow_kind(gid, classes)
        kind_of[INFLOW_LABELS[kind]] = kind
        return INFLOW_LABELS[kind]

    drawn, inflows, category_payees, group_categories, returns = _draw_right(
        d, tally.lines, tally.names, tally.group_names, inflow_label
    )
    for label, value in sorted(inflows.items(), key=lambda kv: -kv[1]):
        d.link(d.node(f"drawn_{kind_of[label]}", label, "inflow"), HUB, value)

    money_in = sum(earned.values(), Decimal(0)) + sum(inflows.values(), Decimal(0))
    _balance(d, money_in, drawn, LEFT_OVER)

    def class_net(classes: Collection[str]) -> Decimal:
        return spent(r.amount for r in rows if not r.is_income and r.activity_class in classes)

    return {
        # Nothing moved: no diagram, not a lone hub.
        "nodes": d.nodes if d.links else [],
        "links": d.links,
        "total_income": total_income,
        "total_expense": drawn,
        "total_spending": class_net(spending_classes),
        "total_savings": class_net({ActivityClass.SAVINGS.value}),
        "total_debt_principal": class_net({ActivityClass.DEBT_PRINCIPAL.value}),
        "total_assigned": None,
        "net": money_in - drawn,
        "category_payees": category_payees,
        "group_categories": group_categories,
        "category_returns": returns,
    }


@dataclass(frozen=True)
class AssignedRow:
    """One month's assignment to one category."""

    category_id: str
    category_name: str
    group_id: str
    group_name: str
    assigned: Decimal


REPLANNED = "Re-planned from other categories"
FROM_READY = ("drawn_ready_to_assign", "From Ready to Assign")
BACK_TO_READY = ("__back_to_ready__", "Back to Ready to Assign")


def budgeted_diagram(rows: Sequence[AssignedRow], total_income: Decimal) -> dict:
    """The budgeted-mode diagram: assignments over the window, NET per
    category.

    Summing only the positive assignments drew money twice when it was
    re-planned: $500 assigned to Groceries and $200 of it later moved to Gas
    drew $700 of groceries-and-gas from $500. A category's months are netted
    first; a category that nets positive is drawn, and what categories gave up
    is a source of its own ("Re-planned from other categories"), so the hub
    balances against Ready to Assign.

    `net` is None: the figure this mode could offer — income less assigned —
    is not the growth of anything, and calling it Net put it beside spent
    mode's Net as if the two measured the same thing.
    """
    d = _Diagram()
    d.node(HUB, "Budget", "budget")
    lines: dict[tuple[str, str], _Line] = {}
    group_names: dict[str, str] = {}
    for r in rows:
        group_names[r.group_id] = r.group_name
        line = lines.setdefault(
            (r.group_id, r.category_id), _Line(r.group_name, r.category_name, r.category_id)
        )
        line.net -= r.assigned  # an assignment is money out of the hub

    drawn, inflows, _payees, group_categories, _returns = _draw_right(
        d, lines, {}, group_names, lambda _g, _c: REPLANNED
    )
    replanned = inflows.get(REPLANNED, Decimal(0))
    if replanned > 0:
        d.link(d.node("drawn_replanned", REPLANNED, "inflow"), HUB, replanned)
    assigned = drawn - replanned
    if assigned > 0:
        d.link(d.node(FROM_READY[0], FROM_READY[1], "inflow"), HUB, assigned)
    _balance(d, max(assigned, Decimal(0)) + replanned, drawn, BACK_TO_READY)

    return {
        "nodes": d.nodes if d.links else [],
        "links": d.links,
        "total_income": total_income,
        "total_expense": drawn,
        # Assignments carry no activity class, so this mode has no split to
        # report. None, not zero: "not claimed here", not "nothing was spent".
        "total_spending": None,
        "total_savings": None,
        "total_debt_principal": None,
        "total_assigned": assigned,
        "net": None,
        "category_payees": {},
        "group_categories": group_categories,
        "category_returns": {},
    }
