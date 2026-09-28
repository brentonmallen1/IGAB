"""Which account types hold cash — the set the runway's "+ savings accounts"
reads (`txn_filters.CASH_SAVINGS_ACCOUNT`).

The runway counted every off-budget savings account, so a budget carrying a
401k and a brokerage account read years of "if income stopped" on a much
smaller pile of cash. Each type is pinned by name: a new built-in type starts
outside the set, and adding one to it is a decision this file records.
"""

import pytest

from igab.domain.account_types import BUILTIN_ACCOUNT_TYPES, CASH_ACCOUNT_TYPE_KEYS


def test_the_cash_types_are_checking_savings_and_cash():
    assert CASH_ACCOUNT_TYPE_KEYS == {"checking", "savings", "cash"}


@pytest.mark.parametrize(
    "key",
    [
        # Saving, and listed by the Savings report, but reached only by a sale,
        # a tax or a penalty: the accounts that inflated the runway.
        "investment",
        # Crypto, a house, a car — even when marked as savings.
        "other_asset",
    ],
)
def test_an_asset_that_is_saving_but_not_cash_is_left_out(key):
    assert key not in CASH_ACCOUNT_TYPE_KEYS


def test_no_liability_holds_cash():
    liabilities = {t.key for t in BUILTIN_ACCOUNT_TYPES if t.classification == "liability"}
    assert liabilities
    assert not liabilities & CASH_ACCOUNT_TYPE_KEYS
