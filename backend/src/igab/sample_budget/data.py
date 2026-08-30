"""The hand-curated sample budget: a plausible household, in two tiers.

STARTER (the default demo): ~35 transactions/month across 13 months
(openings at month −12, full history for the trailing 12). Salary ≈
$4,900/mo against ≈ $4,400/mo of spending and $550/mo of savings buildup.
Dining Out is intentionally overspent in the current month so the budget
page shows a real overspend warning.

FULL (a complex dual-income household, calibrated to a real multi-year YNAB
export — see notes/YNAB-schema-and-relationships.md): everything in the
starter PLUS ~11 more accounts clustered by institution (mortgage + house
fund, HSA cash + investment, 401k + Roth, money market, cash wallet, ESPP,
crypto, one closed legacy checking), a managed mortgage with origination
data, a 0%-promo deferred-interest liability, sinking-fund categories with
self-documenting "$X/12" names, hidden categories with historical activity,
garbled point-of-sale payees, and 30 months of history. The starter is a
strict subset: full-only elements are tagged tiers=("full",).
"""

from decimal import Decimal

from igab.sample_budget.spec import (
    AccountSpec,
    CategorySpec,
    GroupSpec,
    LiabilitySnapshotSpec,
    LiabilitySpec,
    MonthlyTxn,
    OneOffTxn,
    PayeeSpec,
    RelDate,
    SampleBudgetSpec,
    ScheduledSpec,
    SplitLine,
    TargetSpec,
    TierConfig,
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

# Full-tier accounts, clustered by institution the way real households are
MORTGAGE = "Maple St Mortgage"
HOUSE_FUND = "Maple St House Fund"
HSA = "Meridian HSA"
HSA_INVEST = "Meridian HSA Investment"
K401 = "Vertex 401k"
ROTH = "Vertex Roth IRA"
MONEY_MARKET = "Lakeside Money Market"
WALLET = "Harborview Cash"
ESPP = "Northgate ESPP"
CRYPTO = "Crypto Wallet"
LEGACY = "First National Checking (old)"

FULL = ("full",)

# Sinking-fund categories carry their math in the name — the power-user YNAB
# convention ("$1,424/12" = an annual cost budgeted monthly, "~" = estimate)
CAT_CAR_INS = "Car Insurance – $1,416/12"
CAT_PROP_TAX = "Property Tax – ~$2,340/12"
CAT_HOME_MAINT = "Home Maintenance – 1%/12"
CAT_CHRISTMAS = "Christmas – $600/12"
CAT_MORTGAGE = "Mortgage – $2,444/mo"

SAMPLE_BUDGET = SampleBudgetSpec(
    accounts=(
        AccountSpec(CHECKING, "checking", opening_balance=_d("2500.00"), sort_order=0),
        AccountSpec(SAVINGS, "savings", opening_balance=_d("3200.00"), sort_order=1),
        AccountSpec(VISA, "credit_card", opening_balance=_d("-420.00"), sort_order=2),
        AccountSpec(
            CAR_LOAN, "auto_loan", on_budget=False, opening_balance=_d("-9480.00"), sort_order=3
        ),
        AccountSpec(
            BROKERAGE, "investment", on_budget=False, opening_balance=_d("12000.00"), sort_order=4
        ),
        AccountSpec(
            MORTGAGE,
            "mortgage",
            on_budget=False,
            opening_balance=_d("-286000.00"),
            sort_order=5,
            tiers=FULL,
        ),
        AccountSpec(HOUSE_FUND, "savings", opening_balance=_d("4000.00"), sort_order=6, tiers=FULL),
        AccountSpec(
            MONEY_MARKET, "savings", opening_balance=_d("5200.00"), sort_order=7, tiers=FULL
        ),
        AccountSpec(WALLET, "cash", opening_balance=_d("80.00"), sort_order=8, tiers=FULL),
        AccountSpec(
            HSA,
            "other_asset",
            on_budget=False,
            opening_balance=_d("2200.00"),
            sort_order=9,
            tiers=FULL,
        ),
        AccountSpec(
            HSA_INVEST,
            "investment",
            on_budget=False,
            opening_balance=_d("5600.00"),
            sort_order=10,
            tiers=FULL,
        ),
        AccountSpec(
            K401,
            "investment",
            on_budget=False,
            opening_balance=_d("48000.00"),
            sort_order=11,
            tiers=FULL,
        ),
        AccountSpec(
            ROTH,
            "investment",
            on_budget=False,
            opening_balance=_d("15500.00"),
            sort_order=12,
            tiers=FULL,
        ),
        AccountSpec(
            ESPP,
            "other_asset",
            on_budget=False,
            opening_balance=_d("1400.00"),
            sort_order=13,
            tiers=FULL,
        ),
        AccountSpec(
            CRYPTO,
            "other_asset",
            on_budget=False,
            opening_balance=_d("1800.00"),
            sort_order=14,
            tiers=FULL,
        ),
        # A checking account from a previous bank, closed after moving — its
        # ledger nets to zero (income in, rent out) so TBA is untouched
        AccountSpec(LEGACY, "checking", sort_order=15, is_closed=True, tiers=FULL),
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
                # Funded to exactly what the mortgage transfer spends
                CategorySpec(CAT_MORTGAGE, tiers=FULL),
                CategorySpec("Water & Trash", tiers=FULL),
                CategorySpec("Baby Prep", is_archived=True, tiers=FULL),
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
                CategorySpec("Work Lunches", tiers=FULL),
                CategorySpec("Pet Care", tiers=FULL),
                # Hidden but with real history — YNAB budgets accumulate these
                CategorySpec("Old Gym Membership", is_archived=True, tiers=FULL),
                CategorySpec("RC Car Hobby", is_archived=True, tiers=FULL),
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
                CategorySpec("Health Savings", tags=("Savings",), tiers=FULL),
                CategorySpec("Wedding Fund", is_archived=True, tiers=FULL),
                CategorySpec("Moving 2024", is_archived=True, tiers=FULL),
            ),
        ),
        GroupSpec(
            "Long Term – $513/mo",
            tiers=FULL,
            categories=(
                CategorySpec(CAT_CAR_INS, tags=("Long-term expense",), monthly_budget=_d("118.00")),
                CategorySpec(
                    CAT_PROP_TAX, tags=("Long-term expense",), monthly_budget=_d("195.00")
                ),
                CategorySpec(
                    CAT_HOME_MAINT, tags=("Long-term expense",), monthly_budget=_d("150.00")
                ),
                CategorySpec(CAT_CHRISTMAS, monthly_budget=_d("50.00")),
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
        PayeeSpec("Maple St Mortgage Interest", tiers=FULL),
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
        # Duplicate payees for testing cleanup feature
        PayeeSpec("AMAZON.COM", default_category="Shopping"),
        PayeeSpec("Amazon.com AMZN", default_category="Shopping"),
        PayeeSpec("WHOLEFDS MKT", default_category="Groceries"),
        PayeeSpec("Whole Foods Market", default_category="Groceries"),
        PayeeSpec("NETFLIX.COM", default_category="Streaming", tags=("Subscription",)),
        # Full tier: second earner, payroll-side contributions, and the
        # authentically garbled point-of-sale names real bank feeds produce
        PayeeSpec("Harborview Payroll", default_category="Salary", tiers=FULL),
        PayeeSpec("Payroll Contribution", tiers=FULL),
        PayeeSpec("City Water", default_category="Water & Trash", tiers=FULL),
        PayeeSpec("Waste Management", default_category="Water & Trash", tiers=FULL),
        PayeeSpec("County Tax Collector", default_category=CAT_PROP_TAX, tiers=FULL),
        PayeeSpec("Home Depot", default_category=CAT_HOME_MAINT, tiers=FULL),
        PayeeSpec("Chewy", default_category="Pet Care", tiers=FULL),
        PayeeSpec("Aplpay Unhinged Coff", default_category="Coffee", tiers=FULL),
        PayeeSpec("Bulldega Urban Marke", default_category="Groceries", tiers=FULL),
        PayeeSpec("SQ *CORNER BAKE", default_category="Work Lunches", tiers=FULL),
        PayeeSpec("Iron Peak Gym", default_category="Old Gym Membership", tiers=FULL),
        PayeeSpec("RC Superstore", default_category="RC Car Hobby", tiers=FULL),
        PayeeSpec("Two Men & A Truck", default_category="Moving 2024", tiers=FULL),
        PayeeSpec("BuyBuy Baby", default_category="Baby Prep", tiers=FULL),
        PayeeSpec("COSTCO WHSE #0482", tiers=FULL),
        PayeeSpec("Sunrise Bakery", default_category="Dining Out", tiers=FULL),
        PayeeSpec("Round Rock Fuel", default_category="Gas", tiers=FULL),
    ),
    monthly=(
        # A real loan ledger carries its interest: the servicer's monthly
        # charge, a plain row the payoff reading must not subtract from the
        # payment (LOAN_PAYMENT_ROW). The balance moves by payment minus
        # this, as it does at the bank.
        MonthlyTxn(
            MORTGAGE,
            "Maple St Mortgage Interest",
            None,
            2,
            (_d("-1450.00"),),
            memo="Interest charge",
            tiers=FULL,
        ),
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
        # ─── Full tier ───────────────────────────────────────────────────────
        # Second earner: 5th and 20th, ~$4,600/mo
        MonthlyTxn(CHECKING, "Harborview Payroll", "Salary", 5, (_d("2300.00"),), tiers=FULL),
        MonthlyTxn(CHECKING, "Harborview Payroll", "Salary", 20, (_d("2300.00"),), tiers=FULL),
        MonthlyTxn(
            CHECKING,
            "City Water",
            "Water & Trash",
            14,
            (_d("-54.20"), _d("-61.80"), _d("-48.95")),
            tiers=FULL,
        ),
        MonthlyTxn(CHECKING, "Waste Management", "Water & Trash", 3, (_d("-32.00"),), tiers=FULL),
        MonthlyTxn(
            VISA,
            "Chewy",
            "Pet Care",
            13,
            (_d("-52.40"), _d("-48.90"), _d("-55.10")),
            tiers=FULL,
        ),
        # Retirement/HSA accounts move in big, lumpy, payroll-shaped amounts —
        # plain off-budget rows, so they touch net worth but never income
        MonthlyTxn(K401, "Payroll Contribution", None, 5, (_d("1150.00"),), tiers=FULL),
        MonthlyTxn(
            K401,
            "Market Adjustment",
            None,
            27,
            (_d("380.00"), _d("-140.00"), _d("510.00"), _d("220.00")),
            tiers=FULL,
        ),
        MonthlyTxn(
            HSA_INVEST,
            "Market Adjustment",
            None,
            26,
            (_d("90.00"), _d("-35.00"), _d("60.00")),
            tiers=FULL,
        ),
        MonthlyTxn(
            ROTH,
            "Market Adjustment",
            None,
            27,
            (_d("120.00"), _d("-45.00"), _d("160.00")),
            tiers=FULL,
        ),
        MonthlyTxn(ESPP, "Payroll Contribution", None, 20, (_d("231.00"),), tiers=FULL),
        MonthlyTxn(
            CRYPTO,
            "Market Adjustment",
            None,
            24,
            (_d("120.00"), _d("-85.00"), _d("45.00"), _d("-20.00")),
            tiers=FULL,
        ),
        # The cash wallet buys coffee from the garbled-name cart
        MonthlyTxn(
            WALLET,
            "Aplpay Unhinged Coff",
            "Coffee",
            17,
            (_d("-9.50"), _d("-12.25")),
            tiers=FULL,
        ),
        # Monthly Costco run — a second recurring split, lifting the share of
        # split lines toward the ~9% a real register shows
        MonthlyTxn(
            VISA,
            "COSTCO WHSE #0482",
            None,
            19,
            tiers=FULL,
            splits=(
                (
                    SplitLine("Groceries", _d("-58.40")),
                    SplitLine("Household", _d("-31.20")),
                    SplitLine("Pet Care", _d("-24.99")),
                ),
                (
                    SplitLine("Groceries", _d("-49.15")),
                    SplitLine("Household", _d("-42.80")),
                ),
                (
                    SplitLine("Groceries", _d("-63.75")),
                    SplitLine("Household", _d("-27.10")),
                    SplitLine("Pet Care", _d("-24.99")),
                ),
            ),
        ),
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
        # Second earner's office lunches, Tue/Thu
        WeeklyTxn(
            VISA,
            ("SQ *CORNER BAKE", "Thai Garden"),
            "Work Lunches",
            weekdays=(1, 3),
            amounts=(_d("-12.40"), _d("-9.85"), _d("-14.20"), _d("-11.30")),
            tiers=FULL,
        ),
        # Sunday bakery run and the second car's midweek fill-up
        WeeklyTxn(
            CHECKING,
            ("Sunrise Bakery",),
            "Dining Out",
            weekdays=(6,),
            amounts=(_d("-18.40"), _d("-22.75"), _d("-15.90")),
            tiers=FULL,
        ),
        WeeklyTxn(
            CHECKING,
            ("Round Rock Fuel",),
            "Gas",
            weekdays=(3,),
            amounts=(_d("-36.20"), _d("-41.75"), _d("-33.90")),
            tiers=FULL,
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
        # Duplicate payee transactions for testing cleanup feature
        OneOffTxn(RelDate(3, 8), VISA, "AMAZON.COM", _d("-42.99"), "Shopping"),
        OneOffTxn(RelDate(4, 12), VISA, "Amazon.com AMZN", _d("-28.50"), "Shopping"),
        OneOffTxn(RelDate(5, 3), VISA, "AMAZON.COM", _d("-19.99"), "Shopping"),
        OneOffTxn(RelDate(3, 14), CHECKING, "WHOLEFDS MKT", _d("-67.82"), "Groceries"),
        OneOffTxn(RelDate(4, 20), CHECKING, "Whole Foods Market", _d("-54.30"), "Groceries"),
        OneOffTxn(RelDate(6, 6), VISA, "NETFLIX.COM", _d("-15.49"), "Streaming"),
        # ─── Full tier ───────────────────────────────────────────────────────
        # Sinking funds paying out: the semi-annual property tax bill and a
        # water-heater repair, both covered by months of accumulation
        OneOffTxn(
            RelDate(5, 20),
            CHECKING,
            "County Tax Collector",
            _d("-1170.00"),
            CAT_PROP_TAX,
            memo="Semi-annual installment",
            tiers=FULL,
        ),
        OneOffTxn(
            RelDate(8, 9),
            CHECKING,
            "Home Depot",
            _d("-480.00"),
            CAT_HOME_MAINT,
            memo="Water heater element",
            tiers=FULL,
        ),
        OneOffTxn(
            RelDate(3, 11), CHECKING, "Bulldega Urban Marke", _d("-23.60"), "Groceries", tiers=FULL
        ),
        # Hidden categories keep their history — gym cancelled two years ago,
        # a finished hobby, a move, a stocked nursery
        OneOffTxn(
            RelDate(26, 8), VISA, "Iron Peak Gym", _d("-45.00"), "Old Gym Membership", tiers=FULL
        ),
        OneOffTxn(
            RelDate(25, 8), VISA, "Iron Peak Gym", _d("-45.00"), "Old Gym Membership", tiers=FULL
        ),
        OneOffTxn(
            RelDate(24, 8), VISA, "Iron Peak Gym", _d("-45.00"), "Old Gym Membership", tiers=FULL
        ),
        OneOffTxn(RelDate(22, 8), VISA, "RC Superstore", _d("-220.00"), "RC Car Hobby", tiers=FULL),
        OneOffTxn(
            RelDate(19, 23), VISA, "RC Superstore", _d("-140.00"), "RC Car Hobby", tiers=FULL
        ),
        OneOffTxn(
            RelDate(28, 15), CHECKING, "Two Men & A Truck", _d("-850.00"), "Moving 2024", tiers=FULL
        ),
        OneOffTxn(RelDate(16, 6), VISA, "BuyBuy Baby", _d("-310.00"), "Baby Prep", tiers=FULL),
        # The closed legacy checking's whole life: income in, rent out, zero left
        OneOffTxn(
            RelDate(30, 3), LEGACY, "Harborview Payroll", _d("1500.00"), "Salary", tiers=FULL
        ),
        OneOffTxn(
            RelDate(29, 2), LEGACY, "Oakwood Property Mgmt", _d("-750.00"), "Rent", tiers=FULL
        ),
        OneOffTxn(
            RelDate(28, 2), LEGACY, "Oakwood Property Mgmt", _d("-750.00"), "Rent", tiers=FULL
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
        # ─── Full tier ───────────────────────────────────────────────────────
        TransferSpec(
            CHECKING,
            MORTGAGE,
            day=1,
            amount=_d("2444.00"),
            category=CAT_MORTGAGE,
            memo="Mortgage payment (P&I + escrow)",
            tiers=FULL,
        ),
        TransferSpec(
            CHECKING,
            HSA,
            day=6,
            amount=_d("250.00"),
            category="Health Savings",
            memo="HSA contribution",
            tiers=FULL,
        ),
        TransferSpec(
            CHECKING,
            ROTH,
            day=4,
            amount=_d("200.00"),
            category="Investing",
            memo="Roth IRA contribution",
            tiers=FULL,
        ),
        TransferSpec(CHECKING, HOUSE_FUND, day=2, amount=_d("150.00"), tiers=FULL),
        TransferSpec(SAVINGS, MONEY_MARKET, day=17, amount=_d("100.00"), tiers=FULL),
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
        ScheduledSpec(
            CHECKING,
            _d("-2444.00"),
            "monthly",
            day=1,
            transfer_account=MORTGAGE,
            category=CAT_MORTGAGE,
            memo="Mortgage payment",
            tiers=FULL,
        ),
        ScheduledSpec(
            CHECKING,
            _d("2300.00"),
            "twice_monthly",
            day=5,
            second_day_of_month=20,
            payee="Harborview Payroll",
            category="Salary",
            tiers=FULL,
        ),
    ),
    liabilities=(
        # Managed: tracked from the Car Loan account (6.25% APR, 3-year term)
        # The 13 months of $275 transfers already in place give it real payment
        # history and a live payoff projection
        LiabilitySpec(
            name="Car Loan",
            liability_type="auto",
            interest_rate=_d("6.25"),
            minimum_payment=_d("275.00"),
            linked_account=CAR_LOAN,
        ),
        # Unmanaged: Dental Payment Plan (no linked account, manual snapshots)
        # 0% interest payment plan, $95/mo — snapshots spaced 2 months apart
        # to show the balance declining from 1235 → 1045 → 855
        LiabilitySpec(
            name="Dental Payment Plan",
            liability_type="medical",
            interest_rate=_d("0"),
            minimum_payment=_d("95.00"),
            balance=_d("855.00"),
            snapshots=(
                LiabilitySnapshotSpec(RelDate(4, 10), _d("1235.00")),
                LiabilitySnapshotSpec(RelDate(2, 10), _d("1045.00")),
                LiabilitySnapshotSpec(RelDate(0, 1), _d("855.00")),
            ),
        ),
        # Managed mortgage with the full paper trail: origination, principal,
        # 30-year term — exercises the loan-progress and payoff surfaces
        LiabilitySpec(
            name="Maple St Mortgage",
            liability_type="mortgage",
            interest_rate=_d("6.5"),
            minimum_payment=_d("1896.20"),
            linked_account=MORTGAGE,
            origination=RelDate(84, 1),
            original_principal=_d("300000.00"),
            term_months=360,
            tiers=FULL,
        ),
        # Retailer 0%-promo with deferred interest — the "pay it off before
        # the deadline or eat the back-interest" deal
        LiabilitySpec(
            name="Furniture – 0% promo",
            liability_type="other",
            interest_rate=_d("29.99"),
            minimum_payment=_d("95.00"),
            balance=_d("1140.00"),
            snapshots=(
                LiabilitySnapshotSpec(RelDate(3, 5), _d("1425.00")),
                LiabilitySnapshotSpec(RelDate(1, 5), _d("1235.00")),
                LiabilitySnapshotSpec(RelDate(0, 1), _d("1140.00")),
            ),
            promo_end=RelDate(-8, 1),
            promo_deferred_interest=True,
            tiers=FULL,
        ),
    ),
    custom_tags=(("Travel", "blue"),),
    tier_overrides=(("full", TierConfig(months_of_history=30, tba_target=_d("150"))),),
)
