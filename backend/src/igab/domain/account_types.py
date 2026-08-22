"""Built-in account type definitions.

The per-budget `account_types` table is the runtime source of truth — users
can add custom types — and these frozen definitions seed it for every budget
(`igab.services.account_type_service.ensure_account_types_seeded`). The
`description` text doubles as the in-app education copy shown wherever a type
is chosen, so it is written for users, not developers.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinAccountType:
    key: str
    label: str
    classification: str  # 'asset' | 'liability'
    default_on_budget: bool
    description: str
    sort_order: int


BUILTIN_ACCOUNT_TYPES: tuple[BuiltinAccountType, ...] = (
    BuiltinAccountType(
        key="checking",
        label="Checking",
        classification="asset",
        default_on_budget=True,
        description=(
            "Everyday spending account. On budget: its balance funds your "
            "envelopes, and spending from it needs a category. Moving money "
            "between two on-budget accounts is neither income nor spending."
        ),
        sort_order=0,
    ),
    BuiltinAccountType(
        key="savings",
        label="Savings",
        classification="asset",
        default_on_budget=True,
        description=(
            "Money set aside but still yours to plan with. On budget so it can "
            "back envelopes like an emergency fund. Because it is on budget, "
            "moving money here is not counted as saving — the money never left "
            "your budget. Tag a category as Savings if you want it counted."
        ),
        sort_order=1,
    ),
    BuiltinAccountType(
        key="cash",
        label="Cash",
        classification="asset",
        default_on_budget=True,
        description="Physical cash. Works exactly like checking, just tracked by hand.",
        sort_order=2,
    ),
    BuiltinAccountType(
        key="credit_card",
        label="Credit Card",
        classification="liability",
        default_on_budget=True,
        description=(
            "Card debt tracked transaction by transaction. On budget: card "
            "spending uses envelope money, and payments are transfers."
        ),
        sort_order=3,
    ),
    BuiltinAccountType(
        key="loan",
        label="Loan",
        classification="liability",
        default_on_budget=False,
        description=(
            "A mortgage, auto, student, or other loan. Usually off budget — "
            "link a Liability record to it for payoff projections. Money you "
            "send here counts as paying down debt, not spending, so it stays "
            "out of your spending reports."
        ),
        sort_order=4,
    ),
    BuiltinAccountType(
        key="investment",
        label="Investment",
        classification="asset",
        default_on_budget=False,
        description=(
            "Brokerage, retirement (401k, IRA), HSA, or similar. Off budget: it "
            "grows your net worth but isn't spendable envelope money. Money you "
            "move here counts as saving rather than spending. Growth inside the "
            "account — dividends, market movement — is not counted as saving, "
            "because you didn't put it there."
        ),
        sort_order=5,
    ),
    BuiltinAccountType(
        key="other_asset",
        label="Other Asset",
        classification="asset",
        default_on_budget=False,
        description=(
            "Anything else you own that counts toward net worth — property "
            "value, crypto, a manually tracked balance. Off budget, so money "
            "moved here counts as saving rather than spending."
        ),
        sort_order=6,
    ),
    BuiltinAccountType(
        key="other_liability",
        label="Other Liability",
        classification="liability",
        default_on_budget=False,
        description=(
            "Anything else you owe that counts against net worth but isn't "
            "budgeted transaction by transaction. Money you send here counts as "
            "paying down debt rather than spending."
        ),
        sort_order=7,
    ),
)

BUILTIN_ACCOUNT_TYPE_KEYS = frozenset(t.key for t in BUILTIN_ACCOUNT_TYPES)
