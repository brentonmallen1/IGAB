"""The hand-curated sample budget: a plausible small household.

~35 transactions/month across 13 months (openings at month −12, full history
for the trailing 12). Salary ≈ $4,900/mo against ≈ $4,400/mo of spending and
$550/mo of savings buildup. Dining Out is intentionally overspent in the
current month so the budget page shows a real overspend warning.
"""

from decimal import Decimal

from igab.sample_budget.spec import (
    AccountSpec,
    CategorySpec,
    GroupSpec,
    MonthlyTxn,
    OneOffTxn,
    PayeeSpec,
    RelDate,
    SampleBudgetSpec,
    ScheduledSpec,
    SplitLine,
    TargetSpec,
    TransferSpec,
    WeeklyTxn,
)


def _d(value: str) -> Decimal:
    return Decimal(value)


CHECKING = "Checking"
SAVINGS = "Savings"
VISA = "Sapphire Visa"
CAR_LOAN = "Car Loan"
BROKERAGE = "Brokerage"

SAMPLE_BUDGET = SampleBudgetSpec(
    accounts=(
        AccountSpec(CHECKING, "checking", opening_balance=_d("2500.00"), sort_order=0),
        AccountSpec(SAVINGS, "savings", opening_balance=_d("3200.00"), sort_order=1),
        AccountSpec(VISA, "credit_card", opening_balance=_d("-420.00"), sort_order=2),
        AccountSpec(
            CAR_LOAN, "loan", on_budget=False, opening_balance=_d("-9480.00"), sort_order=3
        ),
        AccountSpec(
            BROKERAGE, "tracking", on_budget=False, opening_balance=_d("12000.00"), sort_order=4
        ),
    ),
    groups=(
        GroupSpec(
            "Income",
            is_system=True,
            categories=(
                CategorySpec("Salary"),
                CategorySpec("Other Income"),
            ),
        ),
        GroupSpec(
            "Bills",
            categories=(
                CategorySpec(
                    "Rent",
                    target=TargetSpec("needed_for_spending", _d("1400.00")),
                    monthly_budget=_d("1400.00"),
                ),
                CategorySpec("Electric", tags=("Long-term expense",), monthly_budget=_d("150.00")),
                CategorySpec("Internet", monthly_budget=_d("80.00")),
                CategorySpec("Phone", monthly_budget=_d("65.00")),
                CategorySpec("Streaming", tags=("Subscription",), monthly_budget=_d("30.00")),
            ),
        ),
        GroupSpec(
            "Everyday",
            categories=(
                CategorySpec("Groceries", monthly_budget=_d("560.00")),
                # monthly_budget=None ⇒ funded to exactly what's spent, so the
                # current-month shortfall below is the only overspend anywhere
                CategorySpec("Dining Out", overspend_this_month=_d("45.00")),
                CategorySpec("Coffee", monthly_budget=_d("110.00")),
                CategorySpec("Gas", monthly_budget=_d("120.00")),
                CategorySpec("Shopping", monthly_budget=_d("160.00")),
                CategorySpec("Entertainment", monthly_budget=_d("60.00")),
                CategorySpec("Household", monthly_budget=_d("160.00")),
            ),
        ),
        GroupSpec(
            "Savings Goals",
            categories=(
                CategorySpec(
                    "Emergency Fund",
                    target=TargetSpec("savings_balance", _d("10000.00")),
                    tags=("Savings",),
                    monthly_budget=_d("300.00"),
                    sweep_remainder=True,
                ),
                CategorySpec(
                    "Vacation",
                    target=TargetSpec("monthly_funding", _d("150.00")),
                    tags=("Savings", "Travel"),
                    monthly_budget=_d("150.00"),
                ),
                CategorySpec(
                    "New Laptop",
                    target=TargetSpec("savings_balance", _d("1800.00"), target_date=RelDate(-6, 1)),
                    monthly_budget=_d("150.00"),
                ),
                CategorySpec("Investing", tags=("Savings",)),
            ),
        ),
        GroupSpec(
            "Debt",
            categories=(
                CategorySpec("Car Payment"),
                # Showcase-only CC payment category: linked, $0 assigned, no rows
                CategorySpec("Visa Payment", linked_account=VISA),
            ),
        ),
    ),
    payees=(
        PayeeSpec("Acme Corp Payroll", default_category="Salary"),
        PayeeSpec("Starting Balance"),
        PayeeSpec("Oakwood Property Mgmt", default_category="Rent"),
        PayeeSpec("City Power & Light", default_category="Electric"),
        PayeeSpec("Wave Broadband", default_category="Internet"),
        PayeeSpec("Cricket Wireless", default_category="Phone"),
        PayeeSpec("Netflix", default_category="Streaming", tags=("Subscription",)),
        PayeeSpec("Spotify", default_category="Streaming", tags=("Subscription",)),
        PayeeSpec("Whole Foods", default_category="Groceries"),
        PayeeSpec("Trader Joe's", default_category="Groceries"),
        PayeeSpec("Corner Bistro", default_category="Dining Out"),
        PayeeSpec("Thai Garden", default_category="Dining Out"),
        PayeeSpec("Blue Bottle Coffee", default_category="Coffee"),
        PayeeSpec("Shell", default_category="Gas"),
        PayeeSpec("Target", default_category="Household"),
        PayeeSpec("Amazon", default_category="Shopping"),
        PayeeSpec("AMC Theatres", default_category="Entertainment"),
        PayeeSpec("Jiffy Lube"),
        PayeeSpec("State Farm"),
        PayeeSpec("IRS"),
        PayeeSpec("Best Buy"),
        PayeeSpec("Delta Air Lines", tags=("Travel",)),
        PayeeSpec("Beachside Resort", tags=("Travel",)),
        PayeeSpec("Market Adjustment"),
    ),
    monthly=(
        # Paychecks: 1st and 15th, ~$4,900/mo total
        MonthlyTxn(CHECKING, "Acme Corp Payroll", "Salary", 1, (_d("2450.00"),)),
        MonthlyTxn(CHECKING, "Acme Corp Payroll", "Salary", 15, (_d("2450.00"),)),
        # Fixed bills
        MonthlyTxn(CHECKING, "Oakwood Property Mgmt", "Rent", 1, (_d("-1400.00"),)),
        MonthlyTxn(
            CHECKING,
            "City Power & Light",
            "Electric",
            8,
            # Indexed by calendar month (Jan..Dec): winter and summer peaks
            (
                _d("-142.00"),  # Jan
                _d("-128.00"),  # Feb
                _d("-104.00"),  # Mar
                _d("-82.00"),  # Apr
                _d("-64.00"),  # May
                _d("-78.00"),  # Jun
                _d("-96.00"),  # Jul
                _d("-101.00"),  # Aug
                _d("-84.00"),  # Sep
                _d("-58.00"),  # Oct
                _d("-89.00"),  # Nov
                _d("-125.00"),  # Dec
            ),
        ),
        MonthlyTxn(CHECKING, "Wave Broadband", "Internet", 5, (_d("-79.99"),)),
        MonthlyTxn(CHECKING, "Cricket Wireless", "Phone", 12, (_d("-65.00"),)),
        MonthlyTxn(VISA, "Netflix", "Streaming", 6, (_d("-15.49"),)),
        MonthlyTxn(VISA, "Spotify", "Streaming", 18, (_d("-11.99"),)),
        # Dining out: two sit-down dinners a month on the card
        MonthlyTxn(VISA, "Corner Bistro", "Dining Out", 9, (_d("-72.40"), _d("-64.15"))),
        MonthlyTxn(VISA, "Thai Garden", "Dining Out", 21, (_d("-48.30"), _d("-55.80"))),
        # Gas twice a month
        MonthlyTxn(CHECKING, "Shell", "Gas", 7, (_d("-42.10"), _d("-38.65"), _d("-45.30"))),
        MonthlyTxn(CHECKING, "Shell", "Gas", 22, (_d("-40.25"), _d("-44.80"))),
        # Online shopping + a movie night
        MonthlyTxn(VISA, "Amazon", "Shopping", 11, (_d("-63.20"), _d("-38.47"), _d("-91.06"))),
        MonthlyTxn(VISA, "AMC Theatres", "Entertainment", 24, (_d("-34.00"), _d("-17.00"))),
        # Monthly Target run, split across three envelopes
        MonthlyTxn(
            CHECKING,
            "Target",
            None,
            16,
            splits=(
                (
                    SplitLine("Household", _d("-52.10")),
                    SplitLine("Groceries", _d("-41.24")),
                    SplitLine("Shopping", _d("-25.00")),
                ),
                (
                    SplitLine("Household", _d("-38.90")),
                    SplitLine("Groceries", _d("-33.30")),
                    SplitLine("Shopping", _d("-24.00")),
                ),
                (
                    SplitLine("Household", _d("-61.25")),
                    SplitLine("Groceries", _d("-45.50")),
                    SplitLine("Shopping", _d("-28.00")),
                ),
            ),
        ),
        # Off-budget flavor: the brokerage drifts upward a little each month
        MonthlyTxn(BROKERAGE, "Market Adjustment", None, 28, (_d("250.00"),)),
    ),
    weekly=(
        # Saturday groceries, alternating stores
        WeeklyTxn(
            CHECKING,
            ("Whole Foods", "Trader Joe's"),
            "Groceries",
            weekdays=(5,),
            amounts=(_d("-87.42"), _d("-64.18"), _d("-92.75"), _d("-71.06")),
        ),
        # Coffee Mon/Wed/Fri on the Visa
        WeeklyTxn(
            VISA,
            ("Blue Bottle Coffee",),
            "Coffee",
            weekdays=(0, 2, 4),
            amounts=(_d("-5.75"), _d("-6.25"), _d("-5.75"), _d("-7.50")),
        ),
    ),
    one_offs=(
        # A guaranteed current-month dining spend (day 1 is always ≤ anchor)
        # so the intentional Dining Out overspend exists on any anchor date.
        OneOffTxn(
            RelDate(0, 1),
            VISA,
            "Corner Bistro",
            _d("-85.00"),
            "Dining Out",
            memo="Anniversary dinner",
        ),
        OneOffTxn(
            RelDate(7, 12), CHECKING, "Best Buy", _d("-1650.00"), "New Laptop", memo="MacBook Air"
        ),
        OneOffTxn(
            RelDate(4, 19),
            CHECKING,
            "Jiffy Lube",
            _d("-640.00"),
            "Household",
            memo="Brake pads + rotors",
        ),
        OneOffTxn(RelDate(5, 3), CHECKING, "IRS", _d("920.00"), "Other Income", memo="Tax refund"),
        OneOffTxn(
            RelDate(6, 10),
            CHECKING,
            "State Farm",
            _d("-712.00"),
            "Household",
            memo="Auto insurance, 6 months",
        ),
        # Vacation cluster two months back
        OneOffTxn(RelDate(2, 6), CHECKING, "Delta Air Lines", _d("-424.60"), "Vacation"),
        OneOffTxn(RelDate(2, 14), VISA, "Beachside Resort", _d("-389.00"), "Vacation"),
        OneOffTxn(
            RelDate(2, 15), VISA, "Thai Garden", _d("-86.40"), "Vacation", memo="Vacation dinners"
        ),
    ),
    transfers=(
        TransferSpec(CHECKING, SAVINGS, day=2, amount=_d("400.00"), memo="Monthly savings"),
        TransferSpec(
            CHECKING,
            CAR_LOAN,
            day=10,
            amount=_d("275.00"),
            category="Car Payment",
            memo="Car loan payment",
        ),
        TransferSpec(CHECKING, VISA, day=25, amount=_d("600.00"), memo="Card payment"),
        TransferSpec(
            CHECKING,
            BROKERAGE,
            day=3,
            amount=_d("800.00"),
            category="Investing",
            memo="Monthly index fund buy",
        ),
    ),
    scheduled=(
        ScheduledSpec(
            CHECKING,
            _d("-1400.00"),
            "monthly",
            day=1,
            payee="Oakwood Property Mgmt",
            category="Rent",
        ),
        ScheduledSpec(
            CHECKING,
            _d("2450.00"),
            "twice_monthly",
            day=1,
            second_day_of_month=15,
            payee="Acme Corp Payroll",
            category="Salary",
        ),
        ScheduledSpec(
            VISA,
            _d("-15.49"),
            "monthly",
            day=6,
            payee="Netflix",
            category="Streaming",
        ),
        ScheduledSpec(
            CHECKING,
            _d("-275.00"),
            "monthly",
            day=10,
            transfer_account=CAR_LOAN,
            category="Car Payment",
            memo="Car loan payment",
        ),
        ScheduledSpec(
            CHECKING,
            _d("-712.00"),
            "yearly",
            day=10,
            payee="State Farm",
            category="Household",
            memo="Auto insurance",
            last_occurrence_months_ago=6,
        ),
    ),
    custom_tags=(("Travel", "blue"),),
)
