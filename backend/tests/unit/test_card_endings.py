"""card_last4: whatever a model returned for "the card that paid", as four
digits or nothing."""

import pytest

from igab.domain.card_endings import card_last4


@pytest.mark.parametrize(
    "value",
    [
        "4417",
        "VISA ****4417",
        "XXXXXXXXXXXX4417",
        "Card #: ...4417",
        "ending in 4417",
        "4111111111114417",
        "Card 4417 exp 12/28",
        " 4417 ",
        4417,
    ],
)
def test_the_ending_is_read_out_of_every_spelling(value):
    assert card_last4(value) == "4417"


def test_a_leading_zero_survives_as_text():
    assert card_last4("0417") == "0417"


@pytest.mark.parametrize("value", [None, "", "cash", "***17", "44 17", 417, True, 44.17, ["4417"]])
def test_fewer_than_four_digits_is_no_ending(value):
    # Never padded, never guessed: 417 as a number has already lost its zero.
    assert card_last4(value) is None
