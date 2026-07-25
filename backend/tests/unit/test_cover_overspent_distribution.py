"""Tests for the cover-overspent distribution algorithm.

Algorithm (igab.services.budget_service.distribute_cover):
  1. Shortfall per overspent category = -available (a positive number).
  2. If TBA covers the total shortfall, every category is covered in full.
  3. If TBA is short, each category gets its proportional share rounded DOWN
     to cents, capped at its own shortfall.
  4. TBA <= 0 assigns nothing; no overspent categories yields an empty result.

The hard invariant — and the deliberate difference from fill-targets'
half-even rounding — is that the sum of proposals NEVER exceeds TBA: the
apply endpoint rejects any request whose total exceeds current TBA, so a
preview that overshot by a rounding cent would reject its own apply.
"""

import uuid
from decimal import Decimal

from igab.services.budget_service import distribute_cover


def D(s: str) -> Decimal:
    return Decimal(s)


A, B, C, DD = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class TestFullCover:
    def test_full_cover_when_tba_exceeds_total_overspent(self):
        result = distribute_cover({A: D("60.00"), B: D("40.00")}, D("500.00"))
        assert result[A] == D("60.00")
        assert result[B] == D("40.00")

    def test_full_cover_when_tba_exactly_matches_total(self):
        result = distribute_cover({A: D("60.00"), B: D("40.00")}, D("100.00"))
        assert result[A] == D("60.00")
        assert result[B] == D("40.00")
        assert sum(result.values()) == D("100.00")

    def test_single_category_exact_tba_match(self):
        result = distribute_cover({A: D("100.00")}, D("100.00"))
        assert result[A] == D("100.00")

    def test_three_way_equal_exact_match_no_rounding_loss(self):
        """Full-cover path must not lose cents to division (90/270 * 270 == 90)."""
        result = distribute_cover({A: D("90"), B: D("90"), C: D("90")}, D("270"))
        assert all(v == D("90") for v in result.values())

    def test_cap_at_shortfall_when_one_category_dominates(self):
        """Excess TBA never over-assigns: each category gets exactly its shortfall."""
        result = distribute_cover({A: D("1000.00"), B: D("0.50")}, D("5000.00"))
        assert result[A] == D("1000.00")
        assert result[B] == D("0.50")


class TestPartialCover:
    def test_partial_cover_proportional(self):
        # Total shortfall 600, TBA 300 → 50% coverage each
        result = distribute_cover({A: D("300"), B: D("200"), C: D("100")}, D("300"))
        assert result[A] == D("150.00")
        assert result[B] == D("100.00")
        assert result[C] == D("50.00")
        assert sum(result.values()) == D("300.00")

    def test_partial_cover_heavily_imbalanced(self):
        result = distribute_cover({A: D("900"), B: D("100")}, D("100"))
        assert result[A] == D("90.00")
        assert result[B] == D("10.00")

    def test_partial_cover_never_exceeds_tba(self):
        """The invariant that distinguishes this from fill-targets: no
        rounding tolerance — the sum is strictly bounded by TBA."""
        fixtures = [
            ({A: D("0.01"), B: D("0.01"), C: D("0.01")}, D("0.02")),
            ({A: D("100"), B: D("100"), C: D("100")}, D("1.00")),
            ({A: D("33.33"), B: D("66.67"), C: D("0.01")}, D("50.00")),
            ({A: D("0.03"), B: D("0.03"), C: D("0.03"), DD: D("0.03")}, D("0.10")),
            (
                {uuid.uuid4(): D(str(i * 10 + 1)) for i in range(20)},
                D("500"),
            ),
        ]
        for shortfalls, tba in fixtures:
            result = distribute_cover(shortfalls, tba)
            assert sum(result.values()) <= tba, (
                f"sum {sum(result.values())} exceeds TBA {tba} for {shortfalls}"
            )

    def test_partial_cover_deterministic(self):
        """Same inputs always produce identical proposals."""
        shortfalls = {A: D("123.45"), B: D("67.89"), C: D("10.00")}
        first = distribute_cover(shortfalls, D("75.00"))
        for _ in range(5):
            assert distribute_cover(shortfalls, D("75.00")) == first


class TestNoCover:
    def test_tba_zero_assigns_nothing(self):
        result = distribute_cover({A: D("100"), B: D("200")}, D("0"))
        assert result[A] == D("0")
        assert result[B] == D("0")

    def test_tba_negative_treated_as_zero(self):
        result = distribute_cover({A: D("100")}, D("-50"))
        assert result[A] == D("0")

    def test_no_overspent_categories_returns_empty(self):
        assert distribute_cover({}, D("500")) == {}


class TestRounding:
    def test_rounding_to_cents_thirds(self):
        """3 equal shortfalls, TBA = $1.00 → 33¢ each; the leftover cent
        stays in TBA rather than being force-assigned to one category."""
        result = distribute_cover({A: D("100"), B: D("100"), C: D("100")}, D("1.00"))
        assert result[A] == D("0.33")
        assert result[B] == D("0.33")
        assert result[C] == D("0.33")
        assert sum(result.values()) == D("0.99")

    def test_tiny_shortfalls_round_down_not_up(self):
        """Half-even rounding would give each 0.01 (sum 0.03 > TBA 0.02);
        round-down gives 0.00 each — undershoot is the documented behavior."""
        result = distribute_cover({A: D("0.01"), B: D("0.01"), C: D("0.01")}, D("0.02"))
        assert all(v == D("0.00") for v in result.values())

    def test_results_always_two_decimal_places(self):
        result = distribute_cover({A: D("1"), B: D("2")}, D("1"))
        for v in result.values():
            assert v == v.quantize(D("0.01"))

    def test_partial_share_capped_at_own_shortfall(self):
        """A tiny shortfall alongside a huge one never receives more than
        it needs, even when proportions are extreme."""
        result = distribute_cover({A: D("10000.00"), B: D("0.01")}, D("5000.00"))
        assert result[B] <= D("0.01")
        assert sum(result.values()) <= D("5000.00")

    def test_four_decimal_tba_bounded(self):
        """Money allows 4 decimal places; cent-quantized proposals must still
        stay within a 4dp TBA."""
        result = distribute_cover({A: D("100"), B: D("50")}, D("10.0050"))
        assert sum(result.values()) <= D("10.0050")
