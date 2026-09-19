"""What a gap between the bank's balance and the ledger's actually proves.

The case these are written from: a Harborstone checking account reconciled
clean, and the account page then announced that the bank held $120.00 more
than the ledger and that "something may not have been pulled in — fetch the
last 90 days again". Nothing was missing. Four purchases the bank's own site
showed as posted were still `pending` in the feed, so the user ticked them
cleared before reconciling ($95.00 between them), and a fifth row they typed
by hand ($25.00) had never been near the bank at all. The ledger was AHEAD of
the feed, which is the opposite of the failure the banner named, and the
advice would have spent one of twelve daily bridge requests fetching nothing.

So the gap is decomposed rather than reported whole:

    amount        = reported - ledger_cleared          (+120.00)
    unposted      = cleared rows the bank hasn't posted ( -95.00)
    unexplained   = amount + unposted                  ( +25.00)

and a third reason sits beside those two: a bridge answers from its own last
refresh, so a balance computed before the ledger's newest cleared row is not
measuring the same instant and proves nothing either way.

Figures are invented and rescaled — see the personal-data rule in CLAUDE.md.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from igab.domain.bank_balance import (
    as_of_date,
    describe_drift,
    drift_is_a_fault,
    explain_drift,
)

BANK = Decimal("8420.00")
LEDGER = Decimal("8300.00")
#: Four holds the user ticked cleared because the bank's site showed them.
UNPOSTED = Decimal("-95.00")
#: The hand-typed row the feed has never seen.
REMAINDER = Decimal("25.00")

TODAY = date(2026, 9, 19)
YESTERDAY = date(2026, 9, 18)


def _explain(**kwargs):
    base = {
        "unposted_cleared": Decimal("0"),
        "balance_as_of": None,
        "newest_cleared_on": None,
    }
    return explain_drift(BANK, LEDGER, **{**base, **kwargs})


class TestTheGapDecomposes:
    def test_amount_is_the_whole_gap(self):
        assert _explain().amount == Decimal("120.00")

    def test_unposted_rows_come_out_of_the_gap(self):
        assert _explain(unposted_cleared=UNPOSTED).unexplained == REMAINDER

    def test_a_gap_made_entirely_of_unposted_rows_leaves_nothing(self):
        """The register ran ahead of the feed and nothing else happened."""
        drift = explain_drift(Decimal("8395.00"), LEDGER, unposted_cleared=Decimal("-95.00"))
        assert drift is not None
        assert drift.unexplained == Decimal("0")
        assert drift.reason == "unposted"

    def test_unposted_in_the_other_direction(self):
        """A deposit cleared ahead of the bank puts the ledger above it."""
        drift = explain_drift(
            Decimal("8420.00"), Decimal("8520.00"), unposted_cleared=Decimal("100.00")
        )
        assert drift is not None
        assert drift.amount == Decimal("-100.00")
        assert drift.unexplained == Decimal("0")
        assert drift.reason == "unposted"

    def test_no_reported_balance_is_not_a_gap_of_zero(self):
        assert explain_drift(None, LEDGER) is None

    def test_agreement_is_reported_as_agreement(self):
        drift = explain_drift(LEDGER, LEDGER)
        assert drift is not None
        assert drift.reason == "agree"
        assert not drift.has_drift


class TestStaleness:
    def test_a_balance_older_than_the_newest_cleared_row_is_stale(self):
        drift = _explain(balance_as_of=YESTERDAY, newest_cleared_on=TODAY)
        assert drift is not None
        assert drift.stale
        assert drift.reason == "stale"

    def test_a_balance_as_new_as_the_ledger_is_not_stale(self):
        drift = _explain(balance_as_of=TODAY, newest_cleared_on=TODAY)
        assert drift is not None
        assert not drift.stale
        assert drift.reason == "unexplained"

    def test_no_balance_date_asks_no_staleness_question(self):
        """Every account synced before the column existed. A missing date is
        not evidence of freshness OR of staleness."""
        drift = _explain(balance_as_of=None, newest_cleared_on=TODAY)
        assert drift is not None
        assert not drift.stale

    def test_an_account_with_no_cleared_rows_has_nothing_to_compare(self):
        drift = _explain(balance_as_of=YESTERDAY, newest_cleared_on=None)
        assert drift is not None
        assert not drift.stale

    def test_an_exact_unposted_account_outranks_staleness(self):
        """Precedence is strongest-evidence-first: a complete explanation
        beats 'the comparison is unreliable'."""
        drift = explain_drift(
            Decimal("8395.00"),
            LEDGER,
            unposted_cleared=Decimal("-95.00"),
            balance_as_of=YESTERDAY,
            newest_cleared_on=TODAY,
        )
        assert drift is not None
        assert drift.stale
        assert drift.reason == "unposted"


class TestWhatRaisesAnAlarm:
    def test_an_unreconciled_account_is_never_a_fault(self):
        """A mortgage accrues interest, a 401k moves with the market. The
        user never asserted parity, so there is nothing to have broken."""
        assert not drift_is_a_fault(_explain(), reconciled=False)

    def test_an_unexplained_gap_on_a_reconciled_account_is_a_fault(self):
        assert drift_is_a_fault(_explain(), reconciled=True)

    def test_the_incident_case_is_still_a_fault_for_its_remainder(self):
        """$95.00 of the $120.00 is accounted for; the typed $25.00 is not,
        and that part is worth saying."""
        drift = _explain(unposted_cleared=UNPOSTED)
        assert drift is not None
        assert drift.reason == "unexplained"
        assert drift.unexplained == REMAINDER
        assert drift_is_a_fault(drift, reconciled=True)

    def test_a_fully_unposted_gap_is_not_a_fault(self):
        """The regression this whole change exists for."""
        drift = explain_drift(Decimal("8395.00"), LEDGER, unposted_cleared=Decimal("-95.00"))
        assert not drift_is_a_fault(drift, reconciled=True)

    def test_a_stale_balance_is_not_a_fault(self):
        drift = _explain(balance_as_of=YESTERDAY, newest_cleared_on=TODAY)
        assert not drift_is_a_fault(drift, reconciled=True)

    def test_agreement_is_not_a_fault(self):
        assert not drift_is_a_fault(explain_drift(LEDGER, LEDGER), reconciled=True)

    def test_nothing_reported_is_not_a_fault(self):
        assert not drift_is_a_fault(None, reconciled=True)


class TestTheSentence:
    def test_it_names_the_unexplained_figure_not_the_whole_gap(self):
        """The old line said 'off by 120.00' and sent the user looking for
        $120.00 of missing rows. Only $25.00 was ever missing."""
        drift = _explain(unposted_cleared=UNPOSTED)
        assert drift is not None
        sentence = describe_drift("Harborstone Checking", drift)
        assert "off by 25.00" in sentence
        assert "95.00 of cleared spending not yet posted" in sentence

    def test_with_nothing_unposted_the_two_figures_are_the_same(self):
        drift = _explain()
        assert drift is not None
        sentence = describe_drift("Harborstone Checking", drift)
        assert "off by 120.00" in sentence
        assert "not yet posted" not in sentence


class TestAsOfDate:
    @pytest.mark.parametrize(
        "stamp,expected",
        [
            (datetime(2026, 9, 19, 14, 0, tzinfo=UTC), date(2026, 9, 19)),
            (None, None),
        ],
    )
    def test_whole_utc_days(self, stamp, expected):
        assert as_of_date(stamp) == expected
