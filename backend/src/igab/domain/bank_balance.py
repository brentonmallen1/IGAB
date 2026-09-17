"""Whether the ledger agrees with the balance the bank reports.

The bank's own balance is stored on every sync, and the account page has
always shown the gap when there is one. That was the one number that would
have named a missing $1,240.17 the hour it happened — two dozen rows the sync never
asked for — and it sat on a page nobody had reason to open, while the sync
itself reported success.

The rule is deliberately narrow about *when* a gap is a fault. An account the
user has never reconciled is not one they are holding to the bank's number: a
mortgage accrues interest between statements, a 401k moves with the market,
a loan's payoff figure drifts daily. Flagging those would light the badge
permanently and teach the user to ignore it. An account that has been
reconciled is an account the user has asserted parity for, and on that one a
gap after a sync is news.

Pure: takes the figures, reads nothing.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BalanceDrift:
    """The bank's figure, the ledger's, and the signed difference."""

    reported: Decimal
    ledger_cleared: Decimal

    @property
    def amount(self) -> Decimal:
        """Positive when the bank holds more than the ledger says."""
        return self.reported - self.ledger_cleared


def bank_drift(reported: Decimal | None, ledger_cleared: Decimal) -> Decimal | None:
    """The signed gap for display, or None when the bank has reported nothing."""
    if reported is None:
        return None
    return reported - ledger_cleared


def drift_is_a_fault(
    reported: Decimal | None, ledger_cleared: Decimal, *, reconciled: bool
) -> BalanceDrift | None:
    """The gap the sync should report as a fault, or None.

    Only on a reconciled account, and only when there is a gap. Pending rows
    are already outside `ledger_cleared`, so a purchase the bank has
    authorised but not posted is not a gap.
    """
    if reported is None or not reconciled:
        return None
    if reported == ledger_cleared:
        return None
    return BalanceDrift(reported=reported, ledger_cleared=ledger_cleared)


def describe_drift(account_name: str, drift: BalanceDrift) -> str:
    """One clause for the fault line and the toast."""
    return (
        f"{account_name}: bank reports {_money(drift.reported)}, "
        f"ledger {_money(drift.ledger_cleared)} — off by {_money(abs(drift.amount))}"
    )


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"
