"""The Cash Flow diagram's arithmetic — domain/cash_flow.py.

Every diagram here must balance: what flows into the hub equals what flows
out of it, and each group equals its categories. `_check` asserts that for
every case, so a case that draws a lopsided diagram fails whatever else it
pins.
"""

from decimal import Decimal

from igab.domain.activity_class import ActivityClass
from igab.domain.cash_flow import (
    HUB,
    INCOME_SOURCES_SHOWN,
    PAYEES_SHOWN,
    AssignedRow,
    FlowRow,
    budgeted_diagram,
    spent_diagram,
)

D = Decimal
SPENDING = ActivityClass.SPENDING.value
SAVINGS = ActivityClass.SAVINGS.value
DEBT = ActivityClass.DEBT_PRINCIPAL.value
INCOME = ActivityClass.INCOME.value


def pay(amount: str, payee: str = "Northwind Payserv") -> FlowRow:
    return FlowRow(D(amount), INCOME, True, f"id-{payee}", payee, None, None, None, None)


def row(
    amount: str,
    category: str | None = "Groceries",
    *,
    cls: str = SPENDING,
    payee: str | None = "MegaMart",
    group: str = "Everyday",
) -> FlowRow:
    return FlowRow(
        D(amount),
        cls,
        False,
        f"id-{payee}" if payee else None,
        payee,
        f"cat-{category}" if category else None,
        category,
        f"grp-{group}" if category else None,
        group if category else None,
    )


def _check(diagram: dict) -> dict[tuple[str, str], Decimal]:
    links = {(lk["source"], lk["target"]): lk["value"] for lk in diagram["links"]}
    into_hub = sum(v for (_, t), v in links.items() if t == HUB)
    out_of_hub = sum(v for (s, _), v in links.items() if s == HUB)
    assert into_hub == out_of_hub, "the two sides must balance"
    for (s, t), v in links.items():
        if s == HUB and t.startswith("g_") and diagram["nodes"]:
            children = sum(cv for (cs, _), cv in links.items() if cs == t)
            node_type = next(n["type"] for n in diagram["nodes"] if n["id"] == t)
            if node_type == "category_group":
                assert children == v, f"{t} must equal its categories"
        assert v > 0, "no zero or negative band"
    return links


def names(diagram: dict) -> dict[str, str]:
    return {n["id"]: n["name"] for n in diagram["nodes"]}


class TestSpentIsNet:
    def test_a_refund_comes_off_its_category(self):
        d = spent_diagram([pay("3000"), row("-200"), row("50")])
        links = _check(d)
        assert links[("g_grp-Everyday", "c_grp-Everyday_cat-Groceries")] == D("150")
        assert d["total_spending"] == D("150")

    def test_a_category_that_nets_to_a_refund_is_drawn_on_the_left(self):
        """Refunds were dropped: a month whose returns beat its purchases
        still drew the purchases."""
        d = spent_diagram([pay("1000"), row("80", "Clothing"), row("-100", "Groceries")])
        links = _check(d)
        assert links[("drawn_refunds", HUB)] == D("80")
        assert names(d)["drawn_refunds"] == "Refunds"
        assert "c_grp-Everyday_cat-Clothing" not in names(d)
        # The Spent card is the class net: 100 − 80.
        assert d["total_spending"] == D("20")

    def test_savings_moved_and_drawn_in_one_line_net(self):
        rows = [pay("3000"), row("-500", None, cls=SAVINGS), row("200", None, cls=SAVINGS)]
        d = spent_diagram(rows)
        links = _check(d)
        assert links[(HUB, "g___savings__")] == D("300")
        assert "drawn_savings" not in names(d)
        assert d["total_savings"] == D("300")

    def test_money_drawn_out_of_savings_is_from_savings(self):
        d = spent_diagram([pay("1000"), row("-1500", "Rent"), row("600", None, cls=SAVINGS)])
        links = _check(d)
        assert links[("drawn_savings", HUB)] == D("600")
        assert names(d)["drawn_savings"] == "From savings"
        assert d["total_savings"] == D("-600")

    def test_new_borrowing_is_borrowed(self):
        d = spent_diagram([pay("1000"), row("-1800", "Rent"), row("1000", None, cls=DEBT)])
        links = _check(d)
        assert links[("drawn_debt_principal", HUB)] == D("1000")
        assert names(d)["drawn_debt_principal"] == "Borrowed"


class TestBalance:
    def test_what_is_not_spent_is_left_over(self):
        d = spent_diagram([pay("3000"), row("-1000", "Rent")])
        links = _check(d)
        assert links[(HUB, "g___left_over__")] == D("2000")
        assert names(d)["g___left_over__"] == "Left over"
        assert d["net"] == D("2000")

    def test_spending_beyond_income_is_a_shortfall(self):
        """The client drew one Income node as wide as the outflows — twice
        the month's income, in the window that surfaced it."""
        d = spent_diagram([pay("1000"), row("-2100", "Rent")])
        links = _check(d)
        assert links[("__shortfall__", HUB)] == D("1100")
        assert links[("inc_id-Northwind Payserv", HUB)] == D("1000")
        assert d["net"] == D("-1100")

    def test_net_is_income_vs_expenses_net(self):
        """income − spending − savings moved − debt principal, each netted —
        `ReportService.income_vs_expense`'s formula. The diagram's Net missed
        it by every refund, withdrawal and new loan the gross sums dropped."""
        rows = [
            pay("3000"),
            pay("-200", "Clawback Co"),
            row("-900", "Rent"),
            row("40", "Groceries"),
            row("-300", "Groceries"),
            row("-500", None, cls=SAVINGS),
            row("150", None, cls=SAVINGS),
            row("-400", None, cls=DEBT),
            row("250", None, cls=DEBT),
        ]
        d = spent_diagram(rows)
        _check(d)
        income = D("2800")
        spending = D("900") + D("260")
        assert d["total_income"] == income
        assert d["net"] == income - spending - D("350") - D("150")

    def test_even_money_draws_no_balancing_node(self):
        d = spent_diagram([pay("100"), row("-100")])
        _check(d)
        assert "g___left_over__" not in names(d)
        assert "__shortfall__" not in names(d)
        assert d["net"] == D("0")

    def test_nothing_moved_is_no_diagram(self):
        d = spent_diagram([])
        assert d["nodes"] == [] and d["links"] == []
        assert d["net"] == D("0")


class TestIncomeSources:
    def test_the_sources_add_up_to_income(self):
        """Fifteen sources were drawn and the rest dropped, so the export's
        income links summed short of its TOTAL row."""
        rows = [pay(str(100 + i), f"Payer {i}") for i in range(INCOME_SOURCES_SHOWN + 3)]
        d = spent_diagram([*rows, row("-50")])
        links = _check(d)
        income_links = [v for (s, t), v in links.items() if s.startswith("inc_") and t == HUB]
        assert len(income_links) == INCOME_SOURCES_SHOWN + 1
        assert sum(income_links) == d["total_income"]
        assert names(d)["inc___other__"] == "Other income"
        # The three smallest: 100 + 101 + 102.
        assert links[("inc___other__", HUB)] == D("303")

    def test_a_source_that_nets_negative_is_income_reversed(self):
        d = spent_diagram([pay("1000"), pay("-80", "Clawback Co"), row("-100")])
        links = _check(d)
        assert links[(HUB, "g___income_reversed__")] == D("80")
        assert d["total_income"] == D("920")
        assert d["net"] == D("820")

    def test_a_source_with_no_payee_is_named(self):
        d = spent_diagram([FlowRow(D("50"), INCOME, True, None, None, None, None, None, None)])
        assert names(d)["inc_Unknown Income"] == "Unknown Income"


class TestPayees:
    def test_payees_net_and_a_return_balances_the_level(self):
        d = spent_diagram(
            [pay("1000"), row("-100", payee="MegaMart"), row("30", payee="Corner Store")]
        )
        node = "c_grp-Everyday_cat-Groceries"
        assert d["category_payees"][node] == [{"name": "MegaMart", "total": D("100")}]
        # The drawn payees are 100 against a 70 category: 30 came back.
        assert d["category_returns"][node] == {"name": "Refunds", "total": D("30")}

    def test_the_rest_of_the_payees_are_one_line(self):
        rows = [row(f"-{10 + i}", payee=f"Shop {i}") for i in range(PAYEES_SHOWN + 2)]
        d = spent_diagram([pay("1000"), *rows])
        listed = d["category_payees"]["c_grp-Everyday_cat-Groceries"]
        assert len(listed) == PAYEES_SHOWN + 1
        assert listed[-1] == {"name": "Other payees", "total": D("21")}  # 10 + 11
        assert sum(p["total"] for p in listed) == sum(D(f"{10 + i}") for i in range(12))
        assert "c_grp-Everyday_cat-Groceries" not in d["category_returns"]


def assigned(category: str, amount: str, group: str = "Everyday") -> AssignedRow:
    return AssignedRow(f"cat-{category}", category, f"grp-{group}", group, D(amount))


class TestBudgeted:
    def test_re_planned_money_is_not_drawn_twice(self):
        """$500 assigned to Groceries and $200 of it moved to Gas drew $700
        from $500: only positive assignments were summed."""
        d = budgeted_diagram(
            [assigned("Groceries", "500"), assigned("Groceries", "-200"), assigned("Gas", "200")],
            D("3000"),
        )
        links = _check(d)
        assert links[("g_grp-Everyday", "c_grp-Everyday_cat-Groceries")] == D("300")
        assert links[("g_grp-Everyday", "c_grp-Everyday_cat-Gas")] == D("200")
        assert d["total_expense"] == D("500")
        assert d["total_assigned"] == D("500")
        assert links[("drawn_ready_to_assign", HUB)] == D("500")

    def test_a_category_that_gave_money_up_is_a_source(self):
        d = budgeted_diagram(
            [assigned("Dining", "300"), assigned("Vacation", "400"), assigned("Vacation", "-600")],
            D("0"),
        )
        links = _check(d)
        assert links[("drawn_replanned", HUB)] == D("200")
        assert links[("drawn_ready_to_assign", HUB)] == D("100")
        assert d["total_assigned"] == D("100")

    def test_more_un_assigned_than_assigned_goes_back_to_ready_to_assign(self):
        d = budgeted_diagram([assigned("Dining", "100"), assigned("Vacation", "-300")], D("0"))
        links = _check(d)
        assert links[("drawn_replanned", HUB)] == D("300")
        assert links[(HUB, "g___back_to_ready__")] == D("200")
        assert d["total_assigned"] == D("-200")

    def test_budgeted_mode_claims_no_net_and_no_split(self):
        d = budgeted_diagram([assigned("Rent", "1000")], D("3000"))
        assert d["net"] is None
        assert d["total_spending"] is None
        assert d["total_income"] == D("3000")

    def test_nothing_assigned_is_no_diagram(self):
        d = budgeted_diagram([assigned("Rent", "100"), assigned("Rent", "-100")], D("0"))
        assert d["nodes"] == []
