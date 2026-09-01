"""The probe's non-arithmetic parts: the privacy guard, the formatter it
leans on, the YNAB parsers, and the timeline analysis.

The arithmetic itself is pinned against `domain/cards.py` in
`tests/integration/test_card_probe_agreement.py`; nothing here re-tests it.
"""

import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "card_reserve_probe.py"
_spec = importlib.util.spec_from_file_location("card_reserve_probe", _PROBE_PATH)
assert _spec is not None and _spec.loader is not None
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe  # dataclasses resolves the module through here
_spec.loader.exec_module(probe)

D = Decimal


class TestTheGuard:
    """assert_clean refuses to write anything identifying. These are the
    shapes that leaked before (names, reference numbers, UUIDs) — see the
    personal-data rule in CLAUDE.md."""

    def test_a_clean_report_passes(self):
        probe.assert_clean("Card A: balance -1,900.00 in 2026-08", set())

    def test_a_uuid_is_refused(self):
        with pytest.raises(probe.GuardError):
            probe.assert_clean("row 3f9a1c2e-0b4d-4e6f-8a1b-2c3d4e5f6a7b", set())

    def test_a_five_digit_run_is_refused(self):
        """A loan or account number. Amounts never trip this because the
        formatter puts thousands separators in — pinned below."""
        with pytest.raises(probe.GuardError):
            probe.assert_clean("ref 40182", set())

    def test_a_long_hex_token_is_refused(self):
        with pytest.raises(probe.GuardError):
            probe.assert_clean("id deadbeefcafe0123", set())

    def test_a_real_name_token_is_refused(self):
        with pytest.raises(probe.GuardError):
            probe.assert_clean("paid via Harborstone yesterday", {"harborstone"})

    def test_matching_is_word_bounded(self):
        """'card' inside 'discard' must not trip a deny token."""
        probe.assert_clean("we discard nothing", {"card"})


class TestTheFormatter:
    def test_thousands_separators_keep_digit_runs_short(self):
        """The guard's 5-digit rule is only sound if no legitimate amount can
        contain a 5-digit run. 12345678.90 formats with separators, so the
        longest run is 3."""
        fmt = probe.money_formatter(D("1"))
        assert fmt(D("12345678.90")) == "12,345,678.90"
        probe.assert_clean(fmt(D("12345678.90")), set())

    def test_scaling_preserves_sign_and_ratio(self):
        fmt = probe.money_formatter(D("0.37"))
        assert fmt(D("-100")) == "-37.00"
        assert fmt(D("200")) == "74.00"


class TestPseudonyms:
    def test_names_are_stable_within_a_run(self):
        names = probe.Pseudonyms()
        assert names.get("card", "Sapphire Visa") == names.get("card", "Sapphire Visa")
        assert names.get("card", "Sapphire Visa") != names.get("card", "Nordvik Store Card")

    def test_structural_names_pass_through(self):
        names = probe.Pseudonyms()
        assert names.get("group", "Credit Card Payments") == "Credit Card Payments"
        assert names.get("group", "Income") == "Income"

    def test_deny_tokens_cover_the_real_names_and_not_the_pseudonyms(self):
        names = probe.Pseudonyms()
        label = names.get("card", "Sapphire Visa")
        tokens = names.deny_tokens()
        assert "sapphire" in tokens
        assert "visa" in tokens
        assert "card" not in tokens, "the pseudonym vocabulary must stay usable"
        probe.assert_clean(f"{label}: fine", tokens)

    def test_the_key_file_maps_back(self):
        names = probe.Pseudonyms()
        names.get("card", "Sapphire Visa")
        assert any("Sapphire Visa" in line for line in names.key_lines())


class TestYnabParsers:
    @pytest.mark.parametrize(
        ("raw", "want"),
        [
            ("$1,234.56", D("1234.56")),
            ("-$50.00", D("-50.00")),
            ("($75.25)", D("-75.25")),
            ("0.00", D("0.00")),
            ("", None),
            ("N/A", None),
        ],
    )
    def test_amounts(self, raw, want):
        assert probe._parse_ynab_amount(raw) == want

    @pytest.mark.parametrize(
        ("raw", "want"),
        [
            ("Jul 2020", date(2020, 7, 1)),
            ("2020-07", date(2020, 7, 1)),
            ("nonsense", None),
        ],
    )
    def test_months(self, raw, want):
        assert probe._parse_ynab_month(raw) == want


def _month(legs=None, **overrides):
    base = {leg: D("0") for leg in probe.LEGS}
    base.update(legs or {})
    return probe.CardMonth(
        month=overrides.get("month", date(2026, 1, 1)),
        legs=base,
        set_aside=overrides.get("set_aside", D("0")),
        balance=overrides.get("balance", D("0")),
        riding=overrides.get("riding", D("0")),
    )


class TestTimelineAnalysis:
    def test_the_cumulative_reserve_is_the_signed_sum_of_the_legs(self):
        """Hand-checked: +200 reserved, then a 150 payment and a 100 residual
        in the second month lands at -50."""
        timeline = probe.card_timeline(
            {
                "reserved": {date(2026, 1, 1): D("200")},
                "payments": {date(2026, 2, 1): D("150")},
                "residual": {date(2026, 2, 1): D("100")},
            },
            {},
            {},
        )
        assert [cm.set_aside for cm in timeline] == [D("200"), D("-50")]

    def test_first_breach_names_the_crossing_month_and_the_leg(self):
        timeline = probe.card_timeline(
            {
                "reserved": {date(2026, 1, 1): D("200")},
                "payments": {date(2026, 2, 1): D("150")},
                "residual": {date(2026, 3, 1): D("100")},
            },
            {},
            {},
        )
        breach = probe.first_breach(timeline)
        assert breach is not None
        assert breach.month == date(2026, 3, 1)
        assert breach.set_aside_before == D("50")
        assert breach.set_aside_after == D("-50")
        assert breach.ranked_legs[0] == ("residual", D("-100"))

    def test_a_reserve_that_stays_positive_has_no_breach(self):
        timeline = probe.card_timeline({"reserved": {date(2026, 1, 1): D("200")}}, {}, {})
        assert probe.first_breach(timeline) is None

    def test_worst_months_ranks_by_reserve_delta(self):
        timeline = probe.card_timeline(
            {
                "payments": {date(2026, 1, 1): D("10"), date(2026, 2, 1): D("300")},
                "residual": {date(2026, 3, 1): D("40")},
            },
            {},
            {},
        )
        worst = probe.worst_months(timeline, n=2)
        assert [cm.month for cm in worst] == [date(2026, 2, 1), date(2026, 3, 1)]
