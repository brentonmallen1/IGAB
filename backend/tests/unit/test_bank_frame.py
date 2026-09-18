"""The frame a bank speaks, and the damage the missing rule did.

Every case here is a step in the chain that made a first mortgage sync write
an opening balance of roughly twice the loan and then report it paid off.
"""

from decimal import Decimal

import pytest

from igab.domain.bank_frame import (
    LEDGER,
    LENDER,
    LIABILITY,
    detect_frame,
    normalise,
    resolve_frame,
)
from igab.services.liability_service import LIABILITY_CLASSIFICATION


def test_the_classification_vocabulary_matches_the_service():
    """The domain module spells the classification itself to stay free of the
    service layer; if the service ever renames it, this fails rather than the
    rule silently declining for every account."""
    assert LIABILITY == LIABILITY_CLASSIFICATION


class TestDetectFrame:
    def test_a_liability_reported_positive_is_the_lender_frame(self):
        """The mortgage case: the servicer says '248,900 owed'."""
        assert detect_frame(LIABILITY, Decimal("248900.00")) == LENDER

    def test_a_liability_reported_negative_is_already_the_ledger_frame(self):
        assert detect_frame(LIABILITY, Decimal("-248900.00")) == LEDGER

    def test_an_asset_is_always_ledger(self):
        """A checking account holds a positive balance in both frames, so
        there is nothing to flip — and flipping it would be catastrophic."""
        assert detect_frame("asset", Decimal("11308.73")) == LEDGER
        assert detect_frame("asset", Decimal("-40.00")) == LEDGER

    @pytest.mark.parametrize("balance", [None, Decimal("0")])
    def test_zero_or_missing_balance_is_undecidable(self, balance):
        """None, not LEDGER. A zero balance is evidence of nothing, and
        guessing here would pin the wrong frame for the account's whole life
        on the one sync where the evidence is absent."""
        assert detect_frame(LIABILITY, balance) is None


class TestResolveFrame:
    def test_a_persisted_frame_survives_an_overpaid_card(self):
        """The trap this rule exists for. A lender-frame card that the user
        overpays reports a NEGATIVE balance that month, which detection reads
        as the ledger frame. Re-detecting would flip every row's sign for one
        month. What we already decided wins."""
        assert resolve_frame(LENDER, detect_frame(LIABILITY, Decimal("-40.00"))) == LENDER

    def test_a_persisted_ledger_frame_survives_an_escrow_overage(self):
        """The mirror case: a ledger-frame loan reporting positive once."""
        assert resolve_frame(LEDGER, detect_frame(LIABILITY, Decimal("120.00"))) == LEDGER

    def test_detection_is_used_when_nothing_is_persisted(self):
        assert resolve_frame(None, LENDER) == LENDER

    def test_nothing_known_syncs_verbatim(self):
        """The no-op frame: exactly the behaviour every account had before
        this module existed."""
        assert resolve_frame(None, None) == LEDGER


class TestNormalise:
    def test_normalise_flips_only_in_lender_frame(self):
        assert normalise(LENDER, Decimal("248900.00")) == Decimal("-248900.00")
        assert normalise(LEDGER, Decimal("-248900.00")) == Decimal("-248900.00")

    def test_a_payment_and_the_balance_flip_together(self):
        """The property that makes the anchor safe: one frame decides both, so
        a payment can never end up on the opposite side from the balance it
        pays down — which is what duplicated six rows and doubled the gap."""
        frame = detect_frame(LIABILITY, Decimal("248900.00"))
        assert frame is not None
        balance = normalise(frame, Decimal("248900.00"))
        payment = normalise(frame, Decimal("-1480.00"))
        assert balance < 0  # a debt
        assert payment > 0  # an inflow against it
