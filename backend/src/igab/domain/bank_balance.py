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

It is equally narrow about *what* a gap proves. Ticking a still-pending hold
cleared — because the bank's own site shows it posted and the feed has not
caught up — moves the ledger ahead of the bank by exactly that amount, and
the old rule read that as "rows are missing" and sent the user to refetch 90
days for nothing. A bridge whose `balance-date` predates the ledger's newest
cleared row proves nothing either. Both are separated out here so the only
gap that raises an alarm is the one nothing accounts for.

Pure: takes the figures, reads nothing.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True)
class DriftExplanation:
    """The bank's figure, the ledger's, and what accounts for the gap.

    Three facts, not one number, because the same gap has three very
    different meanings and only one of them is the user's problem:

    - **unposted** — the ledger holds cleared rows the bank has not posted
      against. Ordinary: the register is ahead of the feed, which is what
      ticking a hold cleared is *for*. Resolves itself when the feed
      catches up.
    - **stale** — the balance the bank reported predates activity the ledger
      already holds, so the two are not measuring the same instant and the
      gap is not evidence of anything.
    - **unexplained** — everything else, and the only one that means rows
      may be missing.

    Telling them apart needs `balance-date` and the unposted sum, which is
    why both are stored and served rather than inferred from the gap.
    """

    reported: Decimal
    ledger_cleared: Decimal
    #: Signed sum of rows carrying a bank id the bank has NOT posted against,
    #: which the user (or a match) nonetheless marked cleared. These are
    #: inside `ledger_cleared` and outside `reported` by construction —
    #: see txn_filters.CLEARED_AHEAD_OF_BANK.
    unposted_cleared: Decimal = ZERO
    #: When the bank computed `reported`. None when the bridge did not say.
    as_of: date | None = None
    #: The newest cleared row in the ledger, for comparison against `as_of`.
    newest_cleared_on: date | None = None

    @property
    def amount(self) -> Decimal:
        """Positive when the bank holds more than the ledger says."""
        return self.reported - self.ledger_cleared

    @property
    def unexplained(self) -> Decimal:
        """The part of the gap the unposted rows do not account for.

        `reported` excludes those rows and `ledger_cleared` includes them, so
        a gap made entirely of them is exactly `-unposted_cleared` and this
        is zero. Signed, and in the same frame as `amount`.
        """
        return self.amount + self.unposted_cleared

    @property
    def stale(self) -> bool:
        """The bank's balance predates a cleared row the ledger holds.

        Compared on whole days and only when the bridge gave a date: a
        balance computed this morning cannot be expected to include this
        afternoon's activity, and calling that a fault is how a banner earns
        its way into being ignored.
        """
        if self.as_of is None or self.newest_cleared_on is None:
            return False
        return self.as_of < self.newest_cleared_on

    @property
    def has_drift(self) -> bool:
        return self.amount != ZERO

    @property
    def reason(self) -> str:
        """Why the two figures differ: agree | unposted | stale | unexplained.

        Precedence is strongest-evidence-first. An exact unposted account of
        the whole gap is a complete answer and outranks staleness, which is
        only ever "the comparison is unreliable".
        """
        if not self.has_drift:
            return "agree"
        if self.unexplained == ZERO and self.unposted_cleared != ZERO:
            return "unposted"
        if self.stale:
            return "stale"
        return "unexplained"


def as_of_date(stamp: datetime | None) -> date | None:
    """The bank's balance timestamp as a whole UTC day.

    One home, because three callers ask it — the sync, the health badge and
    the account page — and a day that differs between them would make the
    same account stale on one surface and fresh on another.
    """
    return stamp.astimezone(UTC).date() if stamp is not None else None


def explain_drift(
    reported: Decimal | None,
    ledger_cleared: Decimal,
    *,
    unposted_cleared: Decimal = ZERO,
    balance_as_of: date | None = None,
    newest_cleared_on: date | None = None,
) -> DriftExplanation | None:
    """The gap and its account, or None when the bank has reported nothing.

    The one home for this comparison: the account page's banner, the sync's
    fault line and the health badge all read it, so "is this gap news?" is
    answered once. Returned even when the figures agree — `reason` says so —
    because the page still serves the signed amount.
    """
    if reported is None:
        return None
    return DriftExplanation(
        reported=reported,
        ledger_cleared=ledger_cleared,
        unposted_cleared=unposted_cleared,
        as_of=balance_as_of,
        newest_cleared_on=newest_cleared_on,
    )


def drift_is_a_fault(explanation: DriftExplanation | None, *, reconciled: bool) -> bool:
    """Whether the sync should report this gap as a fault.

    Only on a reconciled account, and only for a gap nothing accounts for.
    An account the user has never reconciled is not one they are holding to
    the bank's number: a mortgage accrues interest between statements, a
    401k moves with the market, a loan's payoff figure drifts daily.
    Flagging those would light the badge permanently and teach the user to
    ignore it.

    An explained gap is not a fault either. Suppressing those does not weaken
    the check that caught two dozen missing rows — `unposted_cleared` is a
    small, precisely bounded set (bank-linked rows with no posting date), so
    subtracting it makes the alarm sharper, not quieter.
    """
    if explanation is None or not reconciled:
        return False
    return explanation.reason == "unexplained"


def describe_drift(account_name: str, drift: DriftExplanation) -> str:
    """One clause for the fault line and the toast.

    Names the *unexplained* figure, which is what the user would have to go
    find. Where the whole gap is unexplained the two are the same number.
    """
    clause = (
        f"{account_name}: bank reports {_money(drift.reported)}, "
        f"ledger {_money(drift.ledger_cleared)} — off by {_money(abs(drift.unexplained))}"
    )
    if drift.unposted_cleared != ZERO:
        clause += f" ({_money(abs(drift.unposted_cleared))} of cleared spending not yet posted)"
    return clause


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
