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


# --- The opening anchor -----------------------------------------------------
#
# A first sync writes one "Starting Balance" row for the gap between what the
# bank reports and what the register already holds: the history that predates
# the sync window. That is a good rule with one missing guard — it trusted the
# gap to BE history.
#
# When a lender's feed arrived in the opposite frame (domain/bank_frame.py),
# the gap was not pre-window history at all. It was the whole balance plus the
# register's own sum plus the payments the sign flip had just duplicated —
# about twice the loan — and the anchor wrote it as fact. Afterwards the drift
# check could not see the damage, because the anchor is defined as the row
# that makes drift zero: the check was reading its own output.
#
# **What this rule can and cannot assert.** Almost nothing about the GAP is
# checkable. The register is one 90-day window and the balance is the whole
# history, so a gap larger than the register is the ordinary case (a card
# carried in with a balance), and a gap of the opposite sign to the register
# is ordinary too (a checking account whose window happens to net negative).
# Two earlier spellings of this rule tested exactly those and would have
# refused the anchor every healthy account depends on.
#
# What IS impossible is the RESULT. The anchor makes the ledger equal the
# reported balance, so a liability account whose bank reports a positive
# balance ends up holding money — and a liability cannot hold money. That is
# the mortgage defect exactly, and it is the whole of what this rule claims.
#
# It is deliberately a backstop rather than the fix. `domain/bank_frame.py`
# normalises the sign at the adapter edge and should mean this never fires;
# it fires when detection had nothing to go on (a zero balance on the run
# that decided the frame) or when a remembered frame is wrong.

_REFUSALS = ("holds_money",)


@dataclass(frozen=True)
class AnchorVerdict:
    """Whether to write an opening-balance row, and why not."""

    reason: str  # "agrees" | "ok" | "holds_money"
    gap: Decimal

    @property
    def should_write(self) -> bool:
        return self.reason == "ok"

    @property
    def refused(self) -> bool:
        """A gap we can see but will not write. Distinct from `agrees`, which
        is the ordinary no-op of a ledger that already matches the bank."""
        return self.reason in _REFUSALS


def anchor_verdict(reported: Decimal, ledger: Decimal, *, is_liability: bool) -> AnchorVerdict:
    """Whether anchoring to `reported` would leave a possible account.

    `ledger` is the cleared balance BEFORE the anchor is written — measuring
    after it is what made the old drift check blind — and is used only for
    the gap, never as a plausibility bound. See the note above for why the
    gap itself carries no signal.
    """
    gap = reported - ledger
    if gap == 0:
        return AnchorVerdict("agrees", gap)
    if is_liability and reported > 0:
        return AnchorVerdict("holds_money", gap)
    return AnchorVerdict("ok", gap)


def describe_refused_anchor(
    account_name: str, verdict: AnchorVerdict, reported: Decimal, ledger: Decimal
) -> str:
    """One clause naming what was refused and what the user should do."""
    return (
        f"{account_name}: the bank reports {_money(reported)} on an account that owes money, "
        f"so no opening balance was written against its register of {_money(ledger)}. "
        "This usually means the feed reports debts as positive — reconcile the account "
        "or check the sign of its imported rows."
    )
