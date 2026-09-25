"""Reading the last four digits of a payment card — pure.

A receipt prints the card that paid in a dozen spellings: "VISA ****4417",
"XXXXXXXXXXXX4417", "Card #: ...4417", "Apple Pay 4417", "ending in 4417".
A model asked for the last four returns some of that text back, or a number,
or a number with its leading zero dropped. This turns whatever came back into
four digits or nothing; it never pads, and it never guesses from fewer than
four digits.
"""

import re

#: A run of four or more digits. Runs, not all digits pooled: "4417 exp
#: 12/28" pooled reads "1228".
_RUN = re.compile(r"\d{4,}")


def card_last4(value: object) -> str | None:
    """The card's last four digits, or None when the value does not carry
    a run of four. The last run wins, and its last four digits — "4417" in
    "****4417", in "4111111111114417", in "Card 4417 exp 12/28"."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        # A model that returned 0417 as a number has already lost the zero;
        # three digits are not an ending.
        value = str(value)
    if not isinstance(value, str):
        return None
    runs = _RUN.findall(value)
    return runs[-1][-4:] if runs else None
