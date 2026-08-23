"""The ledger's split rule — exact, with no tolerance.

The `shared/split_cases.json` block runs the same cases the frontend runs in
`frontend/src/utils/splits.test.ts`. There is no shared code path between
Python and TypeScript, so a rule changed on one side only is caught here or
not at all.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.domain.splits import require_split_balances, split_balances, split_sum

_CASES = json.loads((Path(__file__).resolve().parents[3] / "shared" / "split_cases.json").read_text())


def _ids(cases):
    return [f"{c['total']}={'+'.join(c['legs']) or 'nothing'}" for c in cases]


class TestAgreementWithTheFrontendPredicate:
    @pytest.mark.parametrize("case", _CASES["cases"], ids=_ids(_CASES["cases"]))
    def test_shared_case(self, case):
        legs = [Decimal(a) for a in case["legs"]]
        assert split_balances(Decimal(case["total"]), legs) is case["balances"], case["note"]

    @pytest.mark.parametrize("case", _CASES["backend_only"], ids=_ids(_CASES["backend_only"]))
    def test_sub_cent_case_the_frontend_cannot_express(self, case):
        # Numeric(19,4) can hold these; the editors round at input, so they
        # never reach the client predicate. See the fixture's own comment.
        legs = [Decimal(a) for a in case["legs"]]
        assert split_balances(Decimal(case["total"]), legs) is case["balances"], case["note"]


class TestNoTolerance:
    def test_the_old_tolerance_no_longer_passes(self):
        # `abs(total - amount) > Decimal("0.001")` accepted this on both
        # creation paths, and IntegrityService — which always compared exactly
        # — then reported the row as broken forever.
        assert not split_balances(Decimal("12.50"), [Decimal("10.00"), Decimal("2.4995")])

    def test_exactness_holds_at_scale(self):
        legs = [Decimal("0.01")] * 1000
        assert split_balances(Decimal("10.00"), legs)

    def test_sub_cent_legs_must_still_sum_exactly(self):
        legs = [Decimal("0.0009")] * 999  # 0.8991
        assert not split_balances(Decimal("0.90"), legs)
        assert split_balances(Decimal("0.8991"), legs)

    def test_trailing_zeros_do_not_affect_equality(self):
        # Decimal compares numerically, so scale differences are not drift.
        # Worth pinning: Numeric(19,4) round-trips normalise scale.
        assert split_balances(Decimal("0.90"), [Decimal("0.9000")])
        assert split_balances(Decimal("12.5"), [Decimal("12.50"), Decimal("0.0000")])


class TestEmptyAndDegenerate:
    def test_no_legs_never_balances(self):
        assert not split_balances(Decimal("0"), [])
        assert not split_balances(Decimal("12.50"), [])

    def test_a_zero_parent_with_a_zero_leg_balances(self):
        # Not the API's problem to reject: the editors require a positive
        # parent, and this function answers only "do these add up".
        assert split_balances(Decimal("0"), [Decimal("0")])

    def test_negative_parents_balance_against_negative_legs(self):
        # Outflows are stored negative; the service passes signed amounts.
        assert split_balances(Decimal("-12.50"), [Decimal("-10.00"), Decimal("-2.50")])

    def test_sign_mismatch_does_not_balance(self):
        assert not split_balances(Decimal("12.50"), [Decimal("-10.00"), Decimal("-2.50")])


class TestSplitSum:
    def test_empty_sum_is_zero(self):
        assert split_sum([]) == Decimal("0")

    def test_sums_exactly(self):
        assert split_sum([Decimal("0.10"), Decimal("0.20")]) == Decimal("0.30")


class TestRequireSplitBalances:
    def test_passes_silently_when_balanced(self):
        require_split_balances(Decimal("12.50"), [Decimal("10.00"), Decimal("2.50")])

    def test_raises_with_both_numbers_in_the_message(self):
        with pytest.raises(InvariantViolation) as exc:
            require_split_balances(Decimal("12.50"), [Decimal("10.00")])
        assert "10.00" in str(exc.value) and "12.50" in str(exc.value)

    def test_raises_on_no_lines(self):
        with pytest.raises(InvariantViolation, match="at least one line"):
            require_split_balances(Decimal("12.50"), [])
