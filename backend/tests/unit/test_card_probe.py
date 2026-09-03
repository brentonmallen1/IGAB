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

    def test_generic_words_in_real_names_do_not_break_the_report(self):
        """A real run died because account names carried "The", "Transfer",
        "Payment", "Delta" — words the report itself prints on every budget.
        Those identify nobody and must not be denied; the name's distinctive
        tokens still are."""
        names = probe.Pseudonyms()
        names.get("card", "Delta SkyMiles Visa")
        names.get("env", "The Transfer Payment")
        tokens = names.deny_tokens()
        assert "skymiles" in tokens
        assert "visa" in tokens
        for generic in ("delta", "the", "transfer", "payment"):
            assert generic not in tokens, generic
        probe.assert_clean("worst months (reserve delta): payments -1.00", tokens)

    def test_a_whole_name_leaks_even_when_its_every_word_is_exempt(self):
        """The vocabulary exemption's blind spot, closed: a name spelled
        entirely out of report words has no deniable token, but the full name
        in sequence — across any punctuation — is still a leak."""
        names = probe.Pseudonyms()
        names.get("env", "The Transfer Payment")
        tokens = names.deny_tokens()
        assert "the transfer payment" in tokens
        with pytest.raises(probe.GuardError):
            probe.assert_clean("filed under The Transfer Payment last month", tokens)
        with pytest.raises(probe.GuardError):
            probe.assert_clean("filed under the_transfer-payment yesterday", tokens)
        # The same words apart are the report's own prose, not the name.
        probe.assert_clean("the payment ran past everything; transfer legs: 0", tokens)

    def test_a_name_inside_a_structural_name_is_not_a_phrase(self):
        """An envelope named "Credit Card" must not deny the phrase, or every
        report would trip over its own "Credit Card Payments" heading and the
        credit_card_payment_* summary keys."""
        names = probe.Pseudonyms()
        names.get("env", "Credit Card")
        tokens = names.deny_tokens()
        assert "credit card" not in tokens
        probe.assert_clean("credit_card_payment_assignments_skipped: 0", tokens)


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


class TestTheReportVocabulary:
    """`_REPORT_VOCABULARY` exempts the renderers' own words from the deny
    list. The exemption is safe only while the list is complete AND static:
    this test renders every line both renderers can emit and requires each
    word to be in the vocabulary — add a render line with a new word and this
    is what tells you to list it (until then the guard fails closed on any
    budget whose names use that word). Keep names, payees, and anything
    data-derived OUT of the list; the harvest below emits no real names by
    construction."""

    @staticmethod
    def _maximal_render() -> list[str]:
        m1, m2 = date(2026, 1, 1), date(2026, 2, 1)

        def timeline(neg: bool):
            legs = {
                "reserved": {m1: D("200")},
                "payments": {m2: D("300" if neg else "100")},
            }
            return probe.card_timeline(legs, {m1: D("-40")}, {m1: D("10")})

        contributor = probe.ResidualContributor(
            envelope="Env 01",
            months=2,
            total=D("400"),
            charged_total=D("50"),
            charge_rows=(3, D("120")),
            inflow_kinds={
                "plain": (1, D("40")),
                "transfer_cash": (1, D("10")),
                "transfer_card": (1, D("10")),
                "transfer_tracking": (2, D("330")),
                "transfer_unlinked": (1, D("10")),
            },
            monthly={m1: D("200"), m2: D("200")},
        )

        def report(neg: bool, ynab, has_cat: bool, first_reserving):
            tl = timeline(neg)
            return probe.CardReport(
                label="Card A",
                timeline=tl,
                breach=probe.first_breach(tl),
                worst=probe.worst_months(tl),
                position=probe.card_position(tl[-1].set_aside, tl[-1].balance),
                riding=D("10"),
                residual_contributors=[contributor],
                uncategorized=(2, D("-30")),
                system_filed=(1, D("-20")),
                unpaired_legs=3,
                unclaimed_total=D("-50"),
                first_charge=m1,
                first_reserving=first_reserving,
                has_payment_category=has_cat,
                shadow_envelopes=[("Env 02", D("300"))],
                ynab=ynab,
            )

        data = probe.DbData(
            budget_name="B",
            alembic_revision="b5d2f8c41a97",
            accounts={"a": ("X", "card"), "b": ("Y", "cash"), "c": ("Z", "tracking")},
            card_categories={},
            categories={},
            spendable_ids=["s"],
            assignments={},
            activity={},
            outflows={},
            payments={},
            unclaimed={},
            balance_by_card_month={},
            uncategorized_rows={},
            system_filed_rows={},
            unpaired_legs={},
            first_charge={},
            import_summary={
                **{k: 1 for k in probe._IMPORT_COUNT_KEYS},
                **{k: ("money", "1.00") for k in probe._IMPORT_MONEY_KEYS},
                **{f"parity.{k}": 1 for k in probe._PARITY_COUNT_KEYS},
                **{f"parity.{k}": ("money", "1.00") for k in probe._PARITY_MONEY_KEYS},
            },
            inflow_kinds={},
            charge_rows={},
            ynab_ccp_from_import={},
        )
        fmt = probe.money_formatter(D("1"))
        reports = [
            report(True, (m2, D("-1"), D("2"), 5, 3), False, None),
            report(False, (m2, D("1"), D("1"), 5, 0), True, m2),
        ]
        return [
            probe.render_text(
                reports,
                data,
                fmt,
                True,
                ynab_unreadable=2,
                ynab_empty=True,
                ynab_source="the export zip",
            ),
            probe.render_text(
                [],
                None,
                fmt,
                False,
                None,
                ynab_source="the plan history persisted with the import summary",
            ),
            probe.render_json(reports, data, fmt, True),
        ]

    def test_every_static_render_word_is_in_the_vocabulary(self):
        import re

        emitted: set[str] = set()
        for rendered in self._maximal_render():
            emitted.update(re.findall(r"[a-z]{3,}", rendered.lower()))
        pseudonym_words = {"card", "env", "cash", "tracking", "group", "budget"}
        missing = emitted - probe._REPORT_VOCABULARY - pseudonym_words
        assert not missing, f"add these render words to _REPORT_VOCABULARY: {sorted(missing)}"


class TestPersistedCcpHistory:
    """`_ccp_history_from_summary` reads what newer importers store in
    `budgets.import_summary`. Anything unreadable is skipped, never invented —
    the same posture as the zip parsers above."""

    def test_a_stored_history_is_recovered(self):
        summary = {
            "parity": {
                "ccp_available_history": {
                    "Sapphire Visa": {"2024-01-01": "120.50", "2024-02": -33.1},
                }
            }
        }
        assert probe._ccp_history_from_summary(summary) == {
            "sapphire visa": {
                date(2024, 1, 1): D("120.50"),
                date(2024, 2, 1): D("-33.1"),
            }
        }

    def test_garbage_is_skipped_not_invented(self):
        summary = {
            "parity": {
                "ccp_available_history": {
                    "sapphire visa": {"not a month": "5", "2024-03-01": "nope"},
                    "harborstone": "not a dict",
                }
            }
        }
        assert probe._ccp_history_from_summary(summary) == {}

    @pytest.mark.parametrize(
        "summary", [None, [], "x", {}, {"parity": None}, {"parity": {"ccp_available_history": 7}}]
    )
    def test_absent_or_misshapen_summaries_read_as_empty(self, summary):
        assert probe._ccp_history_from_summary(summary) == {}


class TestResidualContributorRendering:
    """The report must say how a residual stream's money arrived — the whole
    point of the classification — and stay inside the privacy guard."""

    def _report(self) -> "probe.CardReport":
        timeline = probe.card_timeline(
            {"residual": {date(2026, 1, 1): D("200"), date(2026, 2, 1): D("200")}}, {}, {}
        )
        contributor = probe.ResidualContributor(
            envelope="Env 01",
            months=2,
            total=D("400"),
            charged_total=D("50"),
            charge_rows=(7, D("950.00")),
            inflow_kinds={
                "plain": (1, D("40.00")),
                "transfer_tracking": (2, D("360.00")),
            },
            monthly={date(2026, 1, 1): D("200"), date(2026, 2, 1): D("200")},
        )
        return probe.CardReport(
            label="Card A",
            timeline=timeline,
            breach=probe.first_breach(timeline),
            worst=probe.worst_months(timeline),
            position=probe.card_position(timeline[-1].set_aside, D("0")),
            riding=D("0"),
            residual_contributors=[contributor],
            uncategorized=(0, D("0")),
            system_filed=(0, D("0")),
            unpaired_legs=0,
            unclaimed_total=D("0"),
            first_charge=None,
            first_reserving=None,
            has_payment_category=True,
            shadow_envelopes=[],
        )

    def test_the_text_names_the_arrival_kinds_and_the_charge_total(self):
        fmt = probe.money_formatter(D("1"))
        rendered = probe.render_text([self._report()], None, fmt, False, None)
        assert (
            "Env 01: 400.00 over 2 month(s); lifetime charges here 50.00 (monthly nets)" in rendered
        )
        assert "charge rows: 7 row(s), gross 950.00" in rendered
        assert "transfers from OUTSIDE the budget: 2 row(s), net 360.00" in rendered
        assert "plain rows (refund/reward/deposit): 1 row(s), net 40.00" in rendered
        probe.assert_clean(rendered, {"harborstone"})

    def test_the_json_carries_the_monthly_series_for_the_register_hunt(self):
        import json

        fmt = probe.money_formatter(D("1"))
        rendered = probe.render_json([self._report()], None, fmt, False)
        probe.assert_clean(rendered, {"harborstone"})
        entry = json.loads(rendered)["cards"][0]["residual_by_envelope"][0]
        assert entry["charged_lifetime"] == "50.00"
        assert entry["charge_rows"] == {"rows": 7, "gross": "950.00"}
        assert entry["inflows"]["transfer_tracking"] == {"rows": 2, "net": "360.00"}
        assert entry["monthly"] == [
            {"month": "2026-01", "amount": "200.00"},
            {"month": "2026-02", "amount": "200.00"},
        ]
