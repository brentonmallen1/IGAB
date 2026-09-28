"""`domain.card_charges.is_interest_or_fee` — what auto-files to Interest & fees.

Both directions matter. A miss leaves an interest row in "needs a category",
which is the state this exists to end; a false hit files a card payment or a
merchant's purchase into Interest & fees, which is worse — money in the wrong
envelope with nothing asking about it.
"""

import pytest

from igab.domain.card_charges import is_interest_or_fee


@pytest.mark.parametrize(
    "name",
    [
        # Interest, as issuers spell it
        "INTEREST CHARGE ON PURCHASES",
        "Interest Charge",
        "interest charges",
        "INTEREST CHARGED - PURCHASES",
        "Purchase Interest",
        "Interest on purchases",
        "CASH ADVANCE INTEREST",
        "FINANCE CHARGE",
        "Finance charges",
        # The issuer's own fees
        "LATE FEE",
        "Late payment fee",
        "LATE FEE - MAR",
        "Annual Fee",
        "ANNUAL MEMBERSHIP FEE",
        "Membership fee",
        "FOREIGN TRANSACTION FEE",
        "Foreign exchange fee",
        "Foreign fee",
        "CASH ADVANCE FEE",
        "Returned payment fee",
        "RETURNED CHECK FEE",
        "Over-limit fee",
        "OVERLIMIT FEE",
        "Over the limit fee",
        # Bank separators
        "LATE_FEE",
        "Interest   charge",
    ],
)
def test_names_an_issuer_charge(name):
    assert is_interest_or_fee(name) is True


@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        # A payment is money arriving on the card, never a charge.
        "Online payment, thank you",
        "PAYMENT THANK YOU",
        "AUTOPAY PAYMENT - THANK YOU",
        # Merchants that merely contain the words.
        "Fee Fi Fo Fum Bakery",
        "Feeney's Hardware",
        "Coffee Fee Collective",
        "Interesting Books",
        "Compound Interest Brewing",
        "Late Night Pizza",
        "Annual Plant Sale",
        # A savings account's interest is income on another account; the
        # phrases here are the issuer's, not a deposit's.
        "Interest paid",
        "INTEREST EARNED",
        "Corner Market",
    ],
)
def test_leaves_everything_else_alone(name):
    assert is_interest_or_fee(name) is False
