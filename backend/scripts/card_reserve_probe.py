#!/usr/bin/env python3
"""Card reserve probe — a standalone diagnostic for a negative "Ready to pay".

WHAT THIS IS
    One self-contained file. Copy it into a running IGAB backend container and
    run it there; it reads the database the app already points at and writes a
    privacy-scrubbed report explaining each credit card's reserve month by
    month: the five legs, the first month the reserve went below zero, which
    leg drove it, and the months that contribute most of today's negative.

        docker cp card_reserve_probe.py <backend-container>:/tmp/
        docker compose exec backend python /tmp/card_reserve_probe.py
        docker cp <backend-container>:/tmp/card_reserve_report.txt .
        docker cp <backend-container>:/tmp/card_reserve_report.json .

    Read the .txt yourself; the .json is the same content for whoever is
    helping you debug. Optional:

        --budget UUID     pick a budget when the instance has several
        --out PREFIX      output prefix (default /tmp/card_reserve_report)
        --scale FACTOR    multiply every amount by FACTOR before reporting.
                          Ratios and signs — everything the diagnosis needs —
                          survive; the digits do not. Recommended: pick a
                          factor, do not share it.
        --key FILE        write the pseudonym -> real-name mapping to FILE,
                          locally. NEVER send that file to anyone.
        --ynab-zip PATH   also read a YNAB export zip and compare each card's
                          reserve against YNAB's own Credit Card Payments
                          "Available", month by month. Works with no database
                          at all (zip-only mode). Imports made by newer IGAB
                          versions persist that history with the import
                          summary, and the probe reads it from the database
                          automatically — the flag is only needed when the
                          import predates that.

WHAT THE REPORT CONTAINS, AND WHAT IT DOES NOT
    Contains: per-card, per-month aggregate amounts and row counts, with every
    account and category renamed to a pseudonym (Card A, Cash 1, Env 01...).
    Structural names that carry the diagnosis are kept: "Income",
    "Credit Card Payments", "Hidden Categories".

    Does not contain: payee names, memos, or notes (the SQL in this file never
    selects those columns); transaction dates finer than a month; account
    numbers; UUIDs of any kind. Before writing, the report is scanned and the
    script REFUSES to write output containing a run of 5 or more digits, a
    hex/UUID-shaped token, or any word taken from your real account, category,
    or group names. Amounts are printed with thousands separators so a large
    amount can never trip — or hide behind — that digit rule.

WHY THE ARITHMETIC IS COPIED IN HERE
    This file re-implements the reserve walk from igab/domain/cards.py over
    raw SQL instead of importing it. That is deliberate: the deployment this
    runs against may be any version of IGAB, and importing its code would
    report what that version believes rather than what the data says. The
    copy is pinned by tests/integration/test_card_probe_agreement.py, which
    runs both implementations over every scenario in
    igab/sample_budget/card_scenarios.py and requires agreement to the cent.
    If you change the walk in domain/cards.py, that test tells you to change
    it here too.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")

# ─── Inlined domain arithmetic ────────────────────────────────────────────────
# Faithful copies from backend/src/igab/domain/cards.py and carryover.py,
# trimmed to what the probe reads. Keys are plain strings (str(uuid) or names)
# so `sorted(..., key=str)` orders exactly as the domain does.


def next_carryover(end_of_month: Decimal) -> Decimal:
    """carryover.next_carryover — the month-boundary write-off floor."""
    return max(ZERO, end_of_month)


def sum_through(series: dict[date, Decimal], month_start: date) -> Decimal:
    """carryover.sum_through — inclusive unfloored total through a month."""
    return sum((v for m, v in series.items() if m <= month_start), ZERO)


def credit_floored(end_of_month: Decimal, net_card_outflow: Decimal) -> Decimal:
    """cards.credit_floored — the credit-funded part of a month's shortfall."""
    if end_of_month >= ZERO:
        return ZERO
    return min(-end_of_month, max(ZERO, net_card_outflow))


def allocate_capped(amount: Decimal, capacity: dict[str, Decimal]) -> dict[str, Decimal]:
    """cards.allocate_capped — greedy in sorted-key order, each bucket capped."""
    out: dict[str, Decimal] = {}
    remaining = amount
    for bucket in sorted(capacity, key=str):
        take = min(remaining, capacity[bucket])
        if take > ZERO:
            out[bucket] = take
            remaining -= take
    return out


def release_split(
    release: Decimal, floored_exposure: Decimal, funded_reserve: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """cards.release_split — one inflow as (discharged, released, residual)."""
    discharged = min(release, floored_exposure)
    released = min(release - discharged, max(ZERO, funded_reserve))
    return discharged, released, release - discharged - released


def _add(series: dict[str, dict[date, Decimal]], key: str, month: date, amount: Decimal) -> None:
    if amount == ZERO:
        return
    per_key = series.setdefault(key, {})
    per_key[month] = per_key.get(month, ZERO) + amount


@dataclass
class Funding:
    """cards.CardFunding, the fields this probe reads."""

    reservations_by_card: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    released_by_card: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    residual_by_card: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    assignments_by_card: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    covered_by_card: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    riding_by_card: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    floored_by_card: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    end_balances: dict[str, dict[date, Decimal]] = field(default_factory=dict)
    #: residual attributed to the category that carried the inflow — the probe
    #: keeps this where the domain does not, because "which envelope produced
    #: the residual" is the question this whole report exists to answer.
    residual_by_pair: dict[tuple[str, str], dict[date, Decimal]] = field(default_factory=dict)


def card_funding(
    assignments_by_category: dict[str, dict[date, Decimal]],
    activity_by_category: dict[str, dict[date, Decimal]],
    credit_outflows: dict[str, dict[str, dict[date, Decimal]]],
    card_categories: dict[str, str],
) -> Funding:
    """cards.card_funding — the month-major walk, steps 1..5, copied exactly.

    The only additions are the `residual_by_pair` attribution and dropping
    output series the probe never reads (per-category months, repaid).
    """
    out = Funding()

    months_by_category: dict[str, list[date]] = {}
    for category, by_card in credit_outflows.items():
        months_by_category[category] = sorted(
            set(assignments_by_category.get(category, {}))
            | set(activity_by_category.get(category, {}))
            | {m for series in by_card.values() for m in series}
        )
    categories_in_month: dict[date, list[str]] = {}
    for category, months in months_by_category.items():
        for month in months:
            categories_in_month.setdefault(month, []).append(category)

    card_assignments: dict[str, dict[date, Decimal]] = {
        card: assignments_by_category.get(category, {})
        for card, category in card_categories.items()
    }

    carryover: dict[str, Decimal] = {}
    ridden: dict[tuple[str, str], Decimal] = {}
    reserved: dict[tuple[str, str], Decimal] = {}

    all_months = sorted(
        set(categories_in_month) | {m for series in card_assignments.values() for m in series}
    )
    for month in all_months:
        for category in sorted(categories_in_month.get(month, []), key=str):
            nets = {
                card: series[month]
                for card, series in credit_outflows[category].items()
                if month in series
            }

            # 1. Inflows, split three ways.
            repaid = ZERO
            for card, net in nets.items():
                if net >= ZERO:
                    continue
                pair = (category, card)
                discharged, released, residual = release_split(
                    -net, ridden.get(pair, ZERO), reserved.get(pair, ZERO)
                )
                ridden[pair] = ridden.get(pair, ZERO) - discharged
                reserved[pair] = reserved.get(pair, ZERO) - released - residual
                repaid += discharged
                _add(out.released_by_card, card, month, released)
                _add(out.residual_by_card, card, month, residual)
                _add(out.riding_by_card, card, month, -discharged)
                if residual != ZERO:
                    per = out.residual_by_pair.setdefault(pair, {})
                    per[month] = per.get(month, ZERO) + residual

            # 2. The month's end balance, correction folded in.
            end = (
                carryover.get(category, ZERO)
                + assignments_by_category.get(category, {}).get(month, ZERO)
                + activity_by_category.get(category, {}).get(month, ZERO)
                - repaid
            )
            out.end_balances.setdefault(category, {})[month] = end
            carryover[category] = next_carryover(end)

            # 3. What the shortfall put on a card.
            floored = credit_floored(end, sum(nets.values(), ZERO))

            # 4. The charges: floored first, funded is the remainder.
            floored_share = allocate_capped(floored, {c: n for c, n in nets.items() if n > ZERO})
            for card, share in floored_share.items():
                _add(out.floored_by_card, card, month, share)
                _add(out.riding_by_card, card, month, share)
                ridden[(category, card)] = ridden.get((category, card), ZERO) + share
            for card, net in nets.items():
                if net <= ZERO:
                    continue
                delta = net - floored_share.get(card, ZERO)
                reserved[(category, card)] = reserved.get((category, card), ZERO) + delta
                _add(out.reservations_by_card, card, month, delta)

        # 5. The card assignments, against the ride the month just settled.
        for card, series in card_assignments.items():
            amount = series.get(month, ZERO)
            if amount == ZERO:
                continue
            _add(out.assignments_by_card, card, month, amount)
            if amount <= ZERO:
                continue
            pool = {
                cat: exposure
                for (cat, k), exposure in ridden.items()
                if k == card and exposure > ZERO
            }
            for cat, take in allocate_capped(amount, pool).items():
                ridden[(cat, card)] -= take
                _add(out.covered_by_card, card, month, take)
                _add(out.riding_by_card, card, month, -take)

    return out


@dataclass(frozen=True)
class Position:
    """cards.CardPosition — the four terms of the reserve identity."""

    uncovered: Decimal
    over_reserved: Decimal
    short_reserved: Decimal
    card_credit: Decimal


def card_position(set_aside: Decimal, balance: Decimal) -> Position:
    """cards.card_position — signed balance, negative is owed."""
    owed = -balance
    return Position(
        uncovered=max(ZERO, owed - max(ZERO, set_aside)),
        over_reserved=max(ZERO, set_aside - max(ZERO, owed)),
        short_reserved=max(ZERO, -set_aside),
        card_credit=max(ZERO, -owed),
    )


# ─── Timeline analysis ────────────────────────────────────────────────────────

LEGS = ("assigned", "reserved", "released", "residual", "payments")
#: Legs that subtract from the reserve, as they appear in set_aside.
_SIGNS = {"assigned": 1, "reserved": 1, "released": -1, "residual": -1, "payments": -1}


@dataclass
class CardMonth:
    month: date
    legs: dict[str, Decimal]  # this month's deltas, one per LEGS
    set_aside: Decimal  # cumulative through this month
    balance: Decimal  # cumulative ledger through this month
    riding: Decimal  # cumulative uncovered ride

    @property
    def reserve_delta(self) -> Decimal:
        return sum((_SIGNS[leg] * self.legs[leg] for leg in LEGS), ZERO)


def card_timeline(
    legs_by_month: dict[str, dict[date, Decimal]],
    balance_by_month: dict[date, Decimal],
    riding_by_month: dict[date, Decimal],
) -> list[CardMonth]:
    """The reserve month by month: cumulative sums over the five legs."""
    months = sorted(
        {m for series in legs_by_month.values() for m in series}
        | set(balance_by_month)
        | set(riding_by_month)
    )
    out: list[CardMonth] = []
    set_aside = balance = riding = ZERO
    for month in months:
        legs = {leg: legs_by_month.get(leg, {}).get(month, ZERO) for leg in LEGS}
        set_aside += sum((_SIGNS[leg] * legs[leg] for leg in LEGS), ZERO)
        balance += balance_by_month.get(month, ZERO)
        riding += riding_by_month.get(month, ZERO)
        out.append(
            CardMonth(month=month, legs=legs, set_aside=set_aside, balance=balance, riding=riding)
        )
    return out


@dataclass
class Breach:
    month: date
    set_aside_before: Decimal
    set_aside_after: Decimal
    #: (leg, this month's signed contribution to the reserve), most negative first.
    ranked_legs: list[tuple[str, Decimal]]


def first_breach(timeline: list[CardMonth]) -> Breach | None:
    """The first month the cumulative reserve crossed below zero."""
    prev = ZERO
    for cm in timeline:
        if cm.set_aside < ZERO and prev >= ZERO:
            contributions = [(leg, _SIGNS[leg] * cm.legs[leg]) for leg in LEGS]
            contributions.sort(key=lambda t: t[1])
            return Breach(
                month=cm.month,
                set_aside_before=prev,
                set_aside_after=cm.set_aside,
                ranked_legs=[(leg, amt) for leg, amt in contributions if amt != ZERO],
            )
        prev = cm.set_aside
    return None


def worst_months(timeline: list[CardMonth], n: int = 6) -> list[CardMonth]:
    """The months whose reserve delta was most negative — where the drift is."""
    negative = [cm for cm in timeline if cm.reserve_delta < ZERO]
    negative.sort(key=lambda cm: cm.reserve_delta)
    return negative[:n]


# ─── Pseudonyms, formatting, and the output guard ────────────────────────────

#: Names the report may keep verbatim: they are structural, shared by every
#: IGAB budget, and carry the diagnosis.
STRUCTURAL_NAMES = {
    "income",
    "inflow",
    "credit card payments",
    "hidden categories",
    "ready to assign",
}

#: Every word the two renderers can print on their own, harvested from a
#: maximal render and pinned by tests/unit/test_card_probe.py
#: (`test_every_static_render_word_is_in_the_vocabulary`). `deny_tokens`
#: subtracts these: a word this report prints for EVERY budget cannot
#: identify one, and leaving them deniable made the probe refuse to run on
#: any budget whose account or envelope names contain ordinary words — a
#: real run died on names carrying "The", "Transfer", "Payment", "Delta".
#: A name's distinctive tokens (surnames, banks, employers) are never in
#: here, so the guard still catches what it exists to catch; and a new
#: render line whose words are missing fails CLOSED — the guard refuses to
#: write, and the pinning test names the word to add.
_REPORT_VOCABULARY = frozenset((
    "account", "accounts", "activity", "after", "against", "aggregate", "agrees",
    "all", "amount", "amounts", "and", "another", "any", "anything", "are",
    "arrived", "aside", "assign", "assigned", "assignments", "available", "balance", "been",
    "before", "below", "beyond", "breach", "but", "can", "cards", "categories",
    "category", "charge", "charged", "charges", "closed", "compared", "comparison", "contain",
    "contains", "count", "counts", "created", "credit", "dates", "day", "debt",
    "delta", "deposit", "design", "differ", "differing", "divergence", "divergent", "does",
    "early", "either", "elided", "envelope", "envelopes", "ever", "excluded", "expected",
    "export", "exported", "factor", "false", "file", "filed", "final", "first",
    "for", "found", "from", "funded", "gross", "groups", "had", "has", "have",
    "here", "history", "hold", "holds", "identifying", "ids", "igab", "import",
    "imported", "income", "inflows", "kind", "legs", "level", "lifetime", "linked",
    "matches", "may", "memos", "missing", "month", "monthly", "months", "moves",
    "names", "net", "nets", "never", "not", "nothing", "null", "numbers", "ours",
    "outside", "over", "overlay", "parity", "partner", "pay", "payee", "payment",
    "payments", "pending", "per", "persisted", "plain", "plan", "position", "possible",
    "possibly", "predates", "probe", "pseudonymized", "ratios", "read", "ready", "refund",
    "released", "report", "rescaled", "reserve", "reserved", "reserves", "reserving", "residual",
    "revision", "reward", "riding", "rode", "row", "rows", "scaled", "scanned",
    "schema", "sees", "set", "shadow", "short", "signs", "since", "skipped",
    "spendable", "splits", "stripped", "summary", "system", "tagged", "that", "the",
    "theirs", "these", "this", "through", "time", "tokens", "total", "touches",
    "transactions", "transfer", "transfers", "true", "truncated", "typed", "uncategorized",
    "unclaimed", "uncovered", "undisclosed", "unlinked", "unmatched", "unpaired", "unreadable",
    "was", "went", "whose", "window", "with", "worst", "writing", "ynab", "zero", "zip",
))

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_HEX_RUN_RE = re.compile(r"\b[0-9a-fA-F]{12,}\b")
_DIGIT_RUN_RE = re.compile(r"\d{5,}")


class Pseudonyms:
    """Stable pseudonyms for one run. Real names never leave this object
    except through `key_lines()` (the local-only --key file)."""

    def __init__(self) -> None:
        self._map: dict[tuple[str, str], str] = {}
        self._counters: dict[str, int] = {}

    def get(self, kind: str, real_name: str) -> str:
        if real_name.strip().lower() in STRUCTURAL_NAMES:
            return real_name
        key = (kind, real_name)
        if key not in self._map:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            n = self._counters[kind]
            if kind == "card":
                label = f"Card {chr(ord('A') + n - 1)}" if n <= 26 else f"Card {n}"
            elif kind == "cash":
                label = f"Cash {n}"
            elif kind == "tracking":
                label = f"Tracking {n}"
            elif kind == "env":
                label = f"Env {n:02d}"
            elif kind == "group":
                label = f"Group {n}"
            else:
                label = f"{kind.title()} {n}"
            self._map[key] = label
        return self._map[key]

    def deny_tokens(self) -> set[str]:
        """Word tokens from every real name seen — the output must not
        contain any of them. The report's own static vocabulary is exempt:
        a word every report prints identifies nobody, and denying it made
        the probe refuse to run on names like "The Transfer Card".

        The vocabulary exemption is what makes the multi-word PHRASES below
        necessary: a name spelled entirely out of exempt words ("The Transfer
        Payment") has no deniable token left, but the full name appearing in
        sequence is a leak no single word is. Phrases carry spaces, which is
        how `assert_clean` knows to match them across punctuation; ones the
        structural names contain are skipped, or every report would trip on
        its own "Credit Card Payments"."""
        tokens: set[str] = set()
        phrases: set[str] = set()
        for (_, real_name), _label in self._map.items():
            words = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", real_name)]
            tokens.update(words)
            if len(words) >= 2:
                phrase = " ".join(words)
                if not any(phrase in name for name in STRUCTURAL_NAMES):
                    phrases.add(phrase)
        # Words a pseudonym or structural name legitimately contains.
        allowed = {"card", "cash", "env", "tracking", "group", "budget"}
        for name in STRUCTURAL_NAMES:
            allowed.update(re.findall(r"[a-z]{3,}", name))
        return (tokens - allowed - _REPORT_VOCABULARY) | phrases

    def key_lines(self) -> list[str]:
        return [f"{label} = {real}" for (kind, real), label in sorted(self._map.items())]


def money_formatter(scale: Decimal):
    """One formatter for every amount in the report. Thousands separators are
    load-bearing: they keep legitimate large amounts from ever containing a
    5-digit run, which lets the guard treat any such run as an identifier."""

    def fmt(value: Decimal) -> str:
        scaled = (value * scale).quantize(Decimal("0.01"))
        return f"{scaled:,.2f}"

    return fmt


class GuardError(RuntimeError):
    pass


def assert_clean(rendered: str, deny_tokens: set[str]) -> None:
    """Refuse output that still carries something identifying. Same posture as
    scripts/capture_simplefin_fixtures.py: fail loudly, write nothing."""
    if _UUID_RE.search(rendered):
        raise GuardError("output contains a UUID — refusing to write")
    if _HEX_RUN_RE.search(rendered):
        raise GuardError("output contains a long hex token — refusing to write")
    run = _DIGIT_RUN_RE.search(rendered)
    if run:
        raise GuardError(f"output contains a digit run ({run.group()[:4]}…) — refusing to write")
    lowered = rendered.lower()
    for token in deny_tokens:
        if " " in token:
            # A whole real name, as a word sequence: match it across any
            # punctuation/spacing so "Fern-Hollow" still reads as the name.
            pattern = (
                r"\b" + r"[^a-z0-9]{1,8}".join(re.escape(w) for w in token.split()) + r"\b"
            )
        else:
            pattern = rf"\b{re.escape(token)}\b"
        if re.search(pattern, lowered):
            raise GuardError(
                "output contains a word from a real account/category name — refusing to write"
            )


# ─── Database reads ──────────────────────────────────────────────────────────
# Raw SQL mirrors of the repository queries, one comment each naming the
# original. Payee names, memos, and notes are never in any SELECT list.

#: txn_filters.TRANSFER_LEG — partner link, or a payee that names an account.
_SQL_TRANSFER_LEG = (
    "(t.transfer_id IS NOT NULL OR EXISTS ("
    "  SELECT 1 FROM payees py WHERE py.id = t.payee_id AND py.transfer_account_id IS NOT NULL))"
)
#: txn_filters.COUNTERPART_ACCOUNT_ID
_SQL_COUNTERPART = (
    "COALESCE((SELECT p2.account_id FROM transactions p2 WHERE p2.id = t.transfer_id),"
    " (SELECT py2.transfer_account_id FROM payees py2 WHERE py2.id = t.payee_id))"
)
#: txn_filters.COUNTERPART_IS_CASH
_SQL_COUNTERPART_IS_CASH = (
    "EXISTS (SELECT 1 FROM accounts ca WHERE ca.id = " + _SQL_COUNTERPART + " AND NOT ca.is_deleted"
    " AND ca.on_budget AND ca.classification != 'liability')"
)
#: txn_filters.CARD_PAYMENT_FROM_CASH
_SQL_CARD_PAYMENT_FROM_CASH = (
    "(t.amount > 0 AND " + _SQL_TRANSFER_LEG + " AND " + _SQL_COUNTERPART_IS_CASH + ")"
)
#: txn_filters.ON_CARD_ACCOUNT
_SQL_ON_CARD_ACCOUNT = (
    "t.account_id IN (SELECT a.id FROM accounts a WHERE NOT a.is_deleted AND a.on_budget"
    " AND a.classification = 'liability' AND a.budget_id = t.budget_id)"
)
#: txn_filters.ON_BUDGET_ACCOUNT
_SQL_ON_BUDGET_ACCOUNT = (
    "t.account_id IN (SELECT a.id FROM accounts a WHERE NOT a.is_deleted AND a.on_budget"
    " AND a.budget_id = t.budget_id)"
)
#: category_filters.SPENDABLE lifted to the row (txn_filters.row_category).
_SQL_ROW_CATEGORY_SPENDABLE = (
    "EXISTS (SELECT 1 FROM categories c WHERE c.id = t.category_id AND NOT c.is_deleted"
    " AND c.linked_account_id IS NULL AND NOT EXISTS ("
    "   SELECT 1 FROM category_groups g WHERE g.id = c.category_group_id AND g.is_system))"
)
_SQL_MONTH = "date_trunc('month', t.date)::date"

#: Probe-only, no repository original: how each (category, card) pair's
#: INFLOW rows arrived. 'plain' is a refund/reward/deposit typed straight
#: onto the card; the transfer kinds split by what is on the other side —
#: 'transfer_tracking' is a payment from an account outside the budget,
#: which YNAB forces a category onto, and which the funding walk therefore
#: reads as category activity (residual) rather than as a payment. Every
#: row matches exactly one CASE arm, so the buckets partition the pair's
#: inflows by construction; the integration test asserts the arms land
#: where they claim.
_SQL_INFLOW_KINDS = (
    "SELECT t.category_id, t.account_id,"
    " CASE"
    f"  WHEN NOT {_SQL_TRANSFER_LEG} THEN 'plain'"
    "  ELSE COALESCE((SELECT CASE"
    "    WHEN NOT ca.on_budget THEN 'transfer_tracking'"
    "    WHEN ca.classification = 'liability' THEN 'transfer_card'"
    "    ELSE 'transfer_cash' END"
    f"    FROM accounts ca WHERE ca.id = {_SQL_COUNTERPART}"
    "     AND NOT ca.is_deleted),"
    "   'transfer_unlinked')"
    " END AS kind, COUNT(*) AS n, SUM(t.amount) AS net"
    " FROM transactions t"
    " WHERE t.budget_id = :b AND NOT t.is_deleted AND NOT t.is_split"
    " AND t.cleared != 'pending' AND t.amount > 0"
    f" AND {_SQL_ON_CARD_ACCOUNT}"
    f" AND {_SQL_ROW_CATEGORY_SPENDABLE}"
    " GROUP BY 1, 2, 3"
)

#: The other side of the same pair: GROSS charge rows. The walk reserves from
#: MONTHLY NETS, so an envelope whose charges and repayments land in the same
#: months reads as a small `charged_total` while enormous value washes through
#: it — the first real report showed inflow rows 18× the net-charge months,
#: which the gross side resolves into "charges and repayments largely offset,
#: repayments cumulatively ahead". Without this line the reader hunts a
#: phantom trickle-drain instead of a pass-through flow.
_SQL_CHARGE_ROWS = (
    "SELECT t.category_id, t.account_id, COUNT(*) AS n, SUM(-t.amount) AS gross"
    " FROM transactions t"
    " WHERE t.budget_id = :b AND NOT t.is_deleted AND NOT t.is_split"
    " AND t.cleared != 'pending' AND t.amount < 0"
    f" AND {_SQL_ON_CARD_ACCOUNT}"
    f" AND {_SQL_ROW_CATEGORY_SPENDABLE}"
    " GROUP BY 1, 2"
)


@dataclass
class DbData:
    """Everything the analysis needs, read once."""

    budget_name: str
    alembic_revision: str | None
    #: account_id -> (name, kind) where kind is card|cash|tracking
    accounts: dict[str, tuple[str, str]]
    #: card account_id -> linked payment category id (may be missing)
    card_categories: dict[str, str]
    #: category_id -> (name, group_name, in_system_group)
    categories: dict[str, tuple[str, str, bool]]
    spendable_ids: list[str]
    assignments: dict[str, dict[date, Decimal]]
    activity: dict[str, dict[date, Decimal]]
    outflows: dict[str, dict[str, dict[date, Decimal]]]
    payments: dict[str, dict[date, Decimal]]
    unclaimed: dict[str, dict[date, Decimal]]
    balance_by_card_month: dict[str, dict[date, Decimal]]
    #: card -> (count, net) of rows with no category at all
    uncategorized_rows: dict[str, tuple[int, Decimal]]
    #: card -> (count, net) of card rows filed to a system-group category
    system_filed_rows: dict[str, tuple[int, Decimal]]
    #: card -> count of unpaired transfer legs
    unpaired_legs: dict[str, int]
    #: card -> first month with any charge (negative balance row)
    first_charge: dict[str, date]
    #: numeric counters from the persisted import summary (allowlisted keys)
    import_summary: dict[str, object]
    #: (category_id, card_id) -> kind -> (rows, net) for the card's INFLOW
    #: rows filed to a spendable category — how each residual stream's money
    #: actually arrived (plain row vs transfer leg, and from where).
    inflow_kinds: dict[tuple[str, str], dict[str, tuple[int, Decimal]]]
    #: (category_id, card_id) -> (rows, gross) for the pair's CHARGE rows —
    #: the gross side the monthly nets hide (see _SQL_CHARGE_ROWS).
    charge_rows: dict[tuple[str, str], tuple[int, Decimal]]
    #: YNAB's CCP Available per {card name lowercased: {month: amount}},
    #: persisted with the import summary by newer importers. Real card names
    #: stay inside the analysis (matched, never rendered).
    ynab_ccp_from_import: dict[str, dict[date, Decimal]]


async def read_db(database_url: str, budget_id: str | None) -> DbData:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    url = database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:

            async def rows(sql: str, **params):
                result = await conn.execute(text(sql), params)
                return result.fetchall()

            async def scalar(sql: str, **params):
                result = await conn.execute(text(sql), params)
                return result.scalar()

            # Schema context, so version skew is visible instead of mysterious.
            try:
                alembic = await scalar("SELECT version_num FROM alembic_version")
            except Exception:
                alembic = None

            budgets = await rows("SELECT id, name FROM budgets ORDER BY created_at")
            if not budgets:
                raise SystemExit("no budgets in this database")
            if budget_id is None:
                if len(budgets) > 1:
                    print(
                        "This instance has several budgets — pass --budget <id>:", file=sys.stderr
                    )
                    for b in budgets:
                        print(f"  {b.id}  {b.name}", file=sys.stderr)
                    raise SystemExit(2)
                budget_id = str(budgets[0].id)
            budget_name = next((b.name for b in budgets if str(b.id) == budget_id), None)
            if budget_name is None:
                raise SystemExit(f"no budget with id {budget_id}")

            accounts: dict[str, tuple[str, str]] = {}
            for r in await rows(
                "SELECT id, name, on_budget, classification FROM accounts"
                " WHERE budget_id = :b AND NOT is_deleted",
                b=budget_id,
            ):
                if r.on_budget and r.classification == "liability":
                    kind = "card"  # txn_filters.CARD_ACCOUNT
                elif r.on_budget:
                    kind = "cash"  # txn_filters.CASH_ACCOUNT
                else:
                    kind = "tracking"
                accounts[str(r.id)] = (r.name, kind)

            card_categories: dict[str, str] = {}
            categories: dict[str, tuple[str, str, bool]] = {}
            for r in await rows(
                "SELECT c.id, c.name, c.linked_account_id, g.name AS group_name,"
                " g.is_system FROM categories c"
                " JOIN category_groups g ON g.id = c.category_group_id"
                " WHERE c.budget_id = :b AND NOT c.is_deleted",
                b=budget_id,
            ):
                categories[str(r.id)] = (r.name, r.group_name, bool(r.is_system))
                if r.linked_account_id is not None and str(r.linked_account_id) in accounts:
                    card_categories[str(r.linked_account_id)] = str(r.id)

            # category_filters.SPENDABLE via CategoryRepository.spendable_ids
            spendable = [
                str(r.id)
                for r in await rows(
                    "SELECT c.id FROM categories c WHERE c.budget_id = :b AND NOT c.is_deleted"
                    " AND c.linked_account_id IS NULL AND NOT EXISTS ("
                    "  SELECT 1 FROM category_groups g"
                    "  WHERE g.id = c.category_group_id AND g.is_system)",
                    b=budget_id,
                )
            ]

            assignments: dict[str, dict[date, Decimal]] = {}
            for r in await rows(
                "SELECT category_id, month, assigned FROM budget_assignments WHERE budget_id = :b",
                b=budget_id,
            ):
                assignments.setdefault(str(r.category_id), {})[r.month] = Decimal(str(r.assigned))

            # TransactionRepository.sum_all_categories_by_month
            activity: dict[str, dict[date, Decimal]] = {}
            for r in await rows(
                f"SELECT t.category_id, {_SQL_MONTH} AS month, SUM(t.amount) AS total"
                " FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted AND NOT t.is_split"
                " AND t.cleared != 'pending'"
                f" AND {_SQL_ON_BUDGET_ACCOUNT}"
                f" AND {_SQL_ROW_CATEGORY_SPENDABLE}"
                " GROUP BY t.category_id, month",
                b=budget_id,
            ):
                activity.setdefault(str(r.category_id), {})[r.month] = Decimal(str(r.total))

            # TransactionRepository.sum_credit_outflows_by_category
            outflows: dict[str, dict[str, dict[date, Decimal]]] = {}
            for r in await rows(
                f"SELECT t.category_id, t.account_id, {_SQL_MONTH} AS month,"
                " SUM(-t.amount) AS outflow FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted AND NOT t.is_split"
                " AND t.cleared != 'pending'"
                f" AND {_SQL_ON_CARD_ACCOUNT}"
                f" AND {_SQL_ROW_CATEGORY_SPENDABLE}"
                " GROUP BY t.category_id, t.account_id, month",
                b=budget_id,
            ):
                net = Decimal(str(r.outflow))
                if net == ZERO:
                    continue
                outflows.setdefault(str(r.category_id), {}).setdefault(str(r.account_id), {})[
                    r.month
                ] = net

            # TransactionRepository.sum_card_payments_by_month
            payments: dict[str, dict[date, Decimal]] = {}
            for r in await rows(
                f"SELECT t.account_id, {_SQL_MONTH} AS month, SUM(t.amount) AS paid"
                " FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted"
                " AND t.parent_transaction_id IS NULL AND t.cleared != 'pending'"
                f" AND {_SQL_ON_CARD_ACCOUNT} AND {_SQL_CARD_PAYMENT_FROM_CASH}"
                " GROUP BY t.account_id, month",
                b=budget_id,
            ):
                payments.setdefault(str(r.account_id), {})[r.month] = Decimal(str(r.paid))

            # TransactionRepository.sum_unclaimed_card_rows (LEAF shape)
            unclaimed: dict[str, dict[date, Decimal]] = {}
            for r in await rows(
                f"SELECT t.account_id, {_SQL_MONTH} AS month, SUM(t.amount) AS net"
                " FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted AND NOT t.is_split"
                " AND t.cleared != 'pending'"
                f" AND {_SQL_ON_CARD_ACCOUNT}"
                f" AND NOT {_SQL_ROW_CATEGORY_SPENDABLE}"
                f" AND NOT {_SQL_CARD_PAYMENT_FROM_CASH}"
                " GROUP BY t.account_id, month",
                b=budget_id,
            ):
                unclaimed.setdefault(str(r.account_id), {})[r.month] = Decimal(str(r.net))

            # AccountRepository.card_balances, kept per month for the timeline.
            balance_by_card_month: dict[str, dict[date, Decimal]] = {}
            first_charge: dict[str, date] = {}
            for r in await rows(
                f"SELECT t.account_id, {_SQL_MONTH} AS month, SUM(t.amount) AS net,"
                " MIN(CASE WHEN t.amount < 0 THEN t.date END) AS first_charge"
                " FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted"
                " AND t.parent_transaction_id IS NULL AND t.cleared != 'pending'"
                f" AND {_SQL_ON_CARD_ACCOUNT}"
                " GROUP BY t.account_id, month",
                b=budget_id,
            ):
                card = str(r.account_id)
                balance_by_card_month.setdefault(card, {})[r.month] = Decimal(str(r.net))
                if r.first_charge is not None:
                    fc = date(r.first_charge.year, r.first_charge.month, 1)
                    if card not in first_charge or fc < first_charge[card]:
                        first_charge[card] = fc

            uncategorized_rows: dict[str, tuple[int, Decimal]] = {}
            for r in await rows(
                "SELECT t.account_id, COUNT(*) AS n, SUM(t.amount) AS net FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted AND NOT t.is_split"
                " AND t.cleared != 'pending' AND t.category_id IS NULL"
                # A transfer leg is supposed to be uncategorized — counting a
                # payment's own leg as "unfiled spending" points the reader at
                # rows that are fine.
                f" AND NOT {_SQL_TRANSFER_LEG}"
                f" AND {_SQL_ON_CARD_ACCOUNT}"
                " GROUP BY t.account_id",
                b=budget_id,
            ):
                uncategorized_rows[str(r.account_id)] = (int(r.n), Decimal(str(r.net)))

            system_filed_rows: dict[str, tuple[int, Decimal]] = {}
            for r in await rows(
                "SELECT t.account_id, COUNT(*) AS n, SUM(t.amount) AS net FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted AND NOT t.is_split"
                " AND t.cleared != 'pending'"
                f" AND {_SQL_ON_CARD_ACCOUNT}"
                " AND EXISTS (SELECT 1 FROM categories c JOIN category_groups g"
                "   ON g.id = c.category_group_id"
                "   WHERE c.id = t.category_id AND g.is_system)"
                " GROUP BY t.account_id",
                b=budget_id,
            ):
                system_filed_rows[str(r.account_id)] = (int(r.n), Decimal(str(r.net)))

            # txn_filters.UNPAIRED_TRANSFER_LEG, narrowed to card accounts.
            unpaired_legs: dict[str, int] = {}
            for r in await rows(
                "SELECT t.account_id, COUNT(*) AS n FROM transactions t"
                " WHERE t.budget_id = :b AND NOT t.is_deleted"
                " AND t.transfer_id IS NULL AND t.category_id IS NULL"
                " AND EXISTS (SELECT 1 FROM payees py WHERE py.id = t.payee_id"
                "   AND py.transfer_account_id IS NOT NULL)"
                f" AND {_SQL_ON_CARD_ACCOUNT}"
                " GROUP BY t.account_id",
                b=budget_id,
            ):
                unpaired_legs[str(r.account_id)] = int(r.n)

            # How a card's categorized inflows arrived. The funding walk
            # deliberately includes categorized transfer legs
            # (sum_credit_outflows_by_category has no transfer exclusion), so
            # a card paid from an off-budget account — YNAB requires a
            # category on that leg — drains the reserve as residual, not as a
            # payment. This classification is what tells a refund, a partner
            # repayment, and such a payment apart in the report.
            inflow_kinds: dict[tuple[str, str], dict[str, tuple[int, Decimal]]] = {}
            for r in await rows(_SQL_INFLOW_KINDS, b=budget_id):
                pair = (str(r.category_id), str(r.account_id))
                inflow_kinds.setdefault(pair, {})[str(r.kind)] = (int(r.n), Decimal(str(r.net)))

            charge_rows: dict[tuple[str, str], tuple[int, Decimal]] = {}
            for r in await rows(_SQL_CHARGE_ROWS, b=budget_id):
                charge_rows[(str(r.category_id), str(r.account_id))] = (
                    int(r.n),
                    Decimal(str(r.gross)),
                )

            summary_json = await scalar(
                "SELECT import_summary FROM budgets WHERE id = :b", b=budget_id
            )
            import_summary = _allowlisted_import_summary(summary_json)
            ynab_ccp_from_import = _ccp_history_from_summary(summary_json)

        return DbData(
            budget_name=budget_name,
            alembic_revision=alembic,
            accounts=accounts,
            card_categories=card_categories,
            categories=categories,
            spendable_ids=spendable,
            assignments=assignments,
            activity=activity,
            outflows=outflows,
            payments=payments,
            unclaimed=unclaimed,
            balance_by_card_month=balance_by_card_month,
            uncategorized_rows=uncategorized_rows,
            system_filed_rows=system_filed_rows,
            unpaired_legs=unpaired_legs,
            first_charge=first_charge,
            import_summary=import_summary,
            inflow_kinds=inflow_kinds,
            charge_rows=charge_rows,
            ynab_ccp_from_import=ynab_ccp_from_import,
        )
    finally:
        await engine.dispose()


#: import_summary keys that are pure counts or amounts. Free-text fields
#: (errors, tagged category names, parity difference names) carry real names
#: and are deliberately NOT read.
_IMPORT_COUNT_KEYS = (
    "accounts_created",
    "accounts_skipped",
    "accounts_closed",
    "category_groups_created",
    "categories_created",
    "transactions_imported",
    "transactions_excluded",
    "skipped",
    "assignments_imported",
    "transfer_legs_unpaired",
    "transfer_legs_in_splits",
    "categories_tagged",
    "credit_card_payment_assignments_skipped",
    "tracking_account_categories_stripped",
)
_IMPORT_MONEY_KEYS = ("credit_card_payment_reserves_skipped",)
_PARITY_COUNT_KEYS = (
    "matches",
    "categories_compared",
    "categories_differing",
    "categories_pending",
    "categories_unmatched",
    "cards_compared",
    "cards_differing",
)
_PARITY_MONEY_KEYS = (
    "ynab_ready_to_assign",
    "expected_ready_to_assign",
    "igab_ready_to_assign",
    "uncovered_card_debt",
    "uncategorized_net",
)


def _allowlisted_import_summary(summary: object) -> dict[str, object]:
    if not isinstance(summary, dict):
        return {}
    out: dict[str, object] = {}
    for key in _IMPORT_COUNT_KEYS:
        if key in summary:
            out[key] = summary[key]
    for key in _IMPORT_MONEY_KEYS:
        if key in summary:
            out[key] = ("money", summary[key])
    parity = summary.get("parity")
    if isinstance(parity, dict):
        for key in _PARITY_COUNT_KEYS:
            if key in parity:
                out[f"parity.{key}"] = parity[key]
        for key in _PARITY_MONEY_KEYS:
            if key in parity:
                out[f"parity.{key}"] = ("money", parity[key])
    return out


def _ccp_history_from_summary(summary: object) -> dict[str, dict[date, Decimal]]:
    """The YNAB CCP Available history newer importers persist with the parity
    summary — same shape as `read_ynab_ccp_available`, so the overlay works
    without the export zip. Keys are real card names (lowercased); they are
    used only to match cards and never rendered. Unreadable entries are
    skipped, never invented."""
    if not isinstance(summary, dict):
        return {}
    parity = summary.get("parity")
    if not isinstance(parity, dict):
        return {}
    history = parity.get("ccp_available_history")
    if not isinstance(history, dict):
        return {}
    out: dict[str, dict[date, Decimal]] = {}
    for card_name, months in history.items():
        if not isinstance(months, dict):
            continue
        for month_key, amount in months.items():
            month = _parse_ynab_month(str(month_key))
            if month is None:
                continue
            try:
                value = Decimal(str(amount))
            except InvalidOperation:
                continue
            out.setdefault(str(card_name).lower(), {})[month] = value
    return out


# ─── YNAB export overlay ─────────────────────────────────────────────────────


def _parse_ynab_amount(raw: str) -> Decimal | None:
    """A permissive currency parse for the overlay. Unreadable values are
    skipped and counted, never invented — same posture as the app's parser."""
    text = raw.strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[^0-9.,\-]", "", text)
    if text.count(",") and text.count("."):
        text = text.replace(",", "")
    elif text.count(",") == 1 and len(text.split(",")[-1]) == 2:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return -value if negative else value


def _parse_ynab_month(raw: str) -> date | None:
    """'Jul 2020' or '2020-07' -> first of month."""
    raw = raw.strip().strip('"')
    m = re.match(r"^([A-Za-z]{3})\s+(\d{4})$", raw)
    if m:
        months = [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ]
        try:
            return date(int(m.group(2)), months.index(m.group(1).lower()) + 1, 1)
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{2})", raw)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    return None


def read_ynab_ccp_available(zip_path: str) -> tuple[dict[str, dict[date, Decimal]], int]:
    """{card name lowercased: {month: YNAB's CCP Available}} from Plan.csv,
    plus a count of rows whose amount could not be read."""
    out: dict[str, dict[date, Decimal]] = {}
    unreadable = 0
    with zipfile.ZipFile(os.path.expanduser(zip_path)) as zf:
        member = next(
            (n for n in zf.namelist() if n.endswith("Plan.csv") or n.endswith("Budget.csv")), None
        )
        if member is None:
            raise SystemExit("the zip has no Plan.csv / Budget.csv")
        with zf.open(member) as fh:
            reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
            for row in reader:
                group = (row.get("Category Group") or "").strip()
                if group != "Credit Card Payments":
                    continue
                month = _parse_ynab_month(row.get("Month") or "")
                available = _parse_ynab_amount(row.get("Available") or "")
                if month is None or available is None:
                    unreadable += 1
                    continue
                card = (row.get("Category") or "").strip().lower()
                out.setdefault(card, {})[month] = available
    return out, unreadable


# ─── Report assembly ─────────────────────────────────────────────────────────


@dataclass
class ResidualContributor:
    """One envelope's residual stream on one card, largest first."""

    envelope: str
    months: int
    total: Decimal
    #: Lifetime net charges this envelope made on this card (positive months
    #: of the outflow series — what could ever reserve) — distinguishes
    #: "never charged here" from "charged sometimes, but the inflows drowned
    #: it".
    charged_total: Decimal
    #: (rows, gross) of the pair's charge rows. The walk nets by month, so a
    #: pass-through envelope (big charges, near-matching repayments in the
    #: same months) shows a tiny `charged_total` while this stays honest
    #: about the volume — set beside the inflow kinds' gross, it tells a
    #: reimbursement wash apart from a trickle-drain.
    charge_rows: tuple[int, Decimal]
    #: kind -> (rows, net) over the pair's inflow rows: 'plain' (a refund,
    #: reward, reimbursement) or a transfer leg by counterpart —
    #: 'transfer_cash', 'transfer_card', 'transfer_tracking' (a payment from
    #: an account outside the budget), 'transfer_unlinked'.
    inflow_kinds: dict[str, tuple[int, Decimal]]
    #: The full residual series, kept for the top contributors only — the
    #: months to read in the register.
    monthly: dict[date, Decimal]


@dataclass
class CardReport:
    label: str
    timeline: list[CardMonth]
    breach: Breach | None
    worst: list[CardMonth]
    position: Position
    riding: Decimal
    residual_contributors: list[ResidualContributor]
    uncategorized: tuple[int, Decimal]
    system_filed: tuple[int, Decimal]
    unpaired_legs: int
    unclaimed_total: Decimal
    first_charge: date | None
    first_reserving: date | None
    has_payment_category: bool
    shadow_envelopes: list[tuple[str, Decimal]]
    #: (first divergent month, our set_aside, ynab available, months compared,
    #: months divergent) — only when a YNAB zip was given and the card matched.
    ynab: tuple[date, Decimal, Decimal, int, int] | None = None


def analyze(
    data: DbData,
    names: Pseudonyms,
    ynab_ccp: dict[str, dict[date, Decimal]] | None,
) -> list[CardReport]:
    funding = card_funding(data.assignments, data.activity, data.outflows, data.card_categories)

    # Envelope availables for shadow detection: the walk's corrected series
    # where it exists, the plain floored walk elsewhere (budget_service does
    # the same). Only the final month matters here.
    availables: dict[str, Decimal] = {}
    for cat_id in data.spendable_ids:
        series = funding.end_balances.get(cat_id)
        if series is None:
            assigned = data.assignments.get(cat_id, {})
            active = data.activity.get(cat_id, {})
            months = sorted(set(assigned) | set(active))
            carry = ZERO
            for m in months:
                end = carry + assigned.get(m, ZERO) + active.get(m, ZERO)
                carry = next_carryover(end)
            availables[cat_id] = carry
        else:
            last = max(series)
            availables[cat_id] = series[last]

    reports: list[CardReport] = []
    cards = [aid for aid, (_, kind) in data.accounts.items() if kind == "card"]
    for card in sorted(cards, key=lambda c: data.accounts[c][0].lower()):
        real_name, _ = data.accounts[card]
        label = names.get("card", real_name)

        legs_by_month = {
            "assigned": funding.assignments_by_card.get(card, {}),
            "reserved": funding.reservations_by_card.get(card, {}),
            "released": funding.released_by_card.get(card, {}),
            "residual": funding.residual_by_card.get(card, {}),
            "payments": data.payments.get(card, {}),
        }
        timeline = card_timeline(
            legs_by_month,
            data.balance_by_card_month.get(card, {}),
            funding.riding_by_card.get(card, {}),
        )
        if not timeline:
            continue
        final = timeline[-1]
        position = card_position(final.set_aside, final.balance)

        contributors: list[ResidualContributor] = []
        for (cat_id, k), series in funding.residual_by_pair.items():
            if k != card:
                continue
            cat_name = data.categories.get(cat_id, ("?", "?", False))[0]
            charged = sum(
                (v for v in data.outflows.get(cat_id, {}).get(card, {}).values() if v > ZERO),
                ZERO,
            )
            contributors.append(
                ResidualContributor(
                    envelope=names.get("env", cat_name),
                    months=len(series),
                    total=sum(series.values(), ZERO),
                    charged_total=charged,
                    charge_rows=data.charge_rows.get((cat_id, card), (0, ZERO)),
                    inflow_kinds=data.inflow_kinds.get((cat_id, card), {}),
                    monthly=dict(sorted(series.items())),
                )
            )
        contributors.sort(key=lambda c: c.total, reverse=True)
        # The full monthly series is the expensive part; keep it where the
        # diagnosis is and drop it from the tail.
        for c in contributors[3:]:
            c.monthly = {}

        first_reserving: date | None = None
        for leg in ("reserved", "assigned"):
            months = [m for m, v in legs_by_month[leg].items() if v > ZERO]
            if months:
                first = min(months)
                if first_reserving is None or first < first_reserving:
                    first_reserving = first

        shadow: list[tuple[str, Decimal]] = []
        if final.set_aside < ZERO:
            hole = -final.set_aside
            for cat_id, avail in availables.items():
                if avail <= ZERO:
                    continue
                if abs(avail - hole) <= max(Decimal("5"), hole * Decimal("0.02")):
                    cat_name = data.categories.get(cat_id, ("?", "?", False))[0]
                    shadow.append((names.get("env", cat_name), avail))
            shadow.sort(key=lambda t: t[1], reverse=True)

        ynab_line = None
        if ynab_ccp is not None:
            theirs = ynab_ccp.get(real_name.lower())
            if theirs:
                ours = {cm.month: cm.set_aside for cm in timeline}
                compared = divergent = 0
                first_div: tuple[date, Decimal, Decimal] | None = None
                for month in sorted(theirs):
                    if month not in ours:
                        continue
                    compared += 1
                    if abs(ours[month] - theirs[month]) > Decimal("0.01"):
                        divergent += 1
                        if first_div is None:
                            first_div = (month, ours[month], theirs[month])
                if first_div is not None:
                    ynab_line = (*first_div, compared, divergent)
                elif compared:
                    ynab_line = (timeline[-1].month, final.set_aside, final.set_aside, compared, 0)

        reports.append(
            CardReport(
                label=label,
                timeline=timeline,
                breach=first_breach(timeline),
                worst=worst_months(timeline),
                position=position,
                riding=final.riding,
                residual_contributors=contributors[:8],
                uncategorized=data.uncategorized_rows.get(card, (0, ZERO)),
                system_filed=data.system_filed_rows.get(card, (0, ZERO)),
                unpaired_legs=data.unpaired_legs.get(card, 0),
                unclaimed_total=sum(data.unclaimed.get(card, {}).values(), ZERO),
                first_charge=data.first_charge.get(card),
                first_reserving=first_reserving,
                has_payment_category=card in data.card_categories,
                shadow_envelopes=shadow[:3],
                ynab=ynab_line,
            )
        )
    return reports


# ─── Rendering ────────────────────────────────────────────────────────────────

_PREAMBLE = """\
CARD RESERVE PROBE
This report contains: pseudonymized account/envelope names, per-month
aggregate amounts (possibly rescaled), and row counts.
It does not contain: payee names, memos, day-level dates, account numbers,
or ids of any kind. It was scanned for identifying tokens before writing.
"""


def _ym(month: date) -> str:
    return f"{month.year:04d}-{month.month:02d}"


#: How a pair's inflow rows read in the .txt. The keys are the SQL CASE
#: labels; 'transfer_tracking' is the one that means "a payment from an
#: account outside the budget, categorized because YNAB required it".
_KIND_LABELS = {
    "plain": "plain rows (refund/reward/deposit)",
    "transfer_cash": "transfers from budget cash",
    "transfer_card": "transfers from another card",
    "transfer_tracking": "transfers from OUTSIDE the budget",
    "transfer_unlinked": "transfer legs with no linked partner",
}


def _short_rev(revision: str | None) -> str:
    """The alembic revision, truncated to 8 chars. Public information (it
    names a migration file in the repo), but the full 12-char id trips the
    guard's long-hex rule, and the guard's strictness is worth more than the
    last four characters."""
    return revision[:8] if revision else "unknown"


def render_text(
    reports: list[CardReport],
    data: DbData | None,
    fmt,
    scaled: bool,
    ynab_unreadable: int | None,
    ynab_empty: bool = False,
    ynab_source: str | None = None,
) -> str:
    lines: list[str] = [_PREAMBLE]
    if scaled:
        lines.append("Amounts are RESCALED by an undisclosed factor; ratios and signs hold.\n")
    if data is not None:
        lines.append(f"Schema revision: {_short_rev(data.alembic_revision)}")
        kinds = {}
        for _, (_, kind) in data.accounts.items():
            kinds[kind] = kinds.get(kind, 0) + 1
        lines.append(
            "Accounts: "
            + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
            + f"; spendable envelopes: {len(data.spendable_ids)}"
        )
        if data.import_summary:
            lines.append("\nIMPORT SUMMARY (persisted at import time)")
            for key, value in data.import_summary.items():
                if isinstance(value, tuple) and value[0] == "money":
                    try:
                        rendered = fmt(Decimal(str(value[1])))
                    except InvalidOperation:
                        rendered = "?"
                    lines.append(f"  {key}: {rendered}")
                else:
                    lines.append(f"  {key}: {value}")
    if ynab_source:
        lines.append(f"\nYNAB overlay read from {ynab_source}.")
    if ynab_unreadable:
        lines.append(
            f"\nYNAB overlay: {ynab_unreadable} plan rows had unreadable amounts (skipped)"
        )
    if ynab_empty:
        lines.append(
            "\nYNAB overlay: the export's plan has NO 'Credit Card Payments' rows —"
            " either the budget had no cards in the exported window, or the export"
            " is truncated. No YNAB comparison is possible from this file."
        )
    if not reports:
        lines.append("\nNo card accounts found — nothing to report.")

    for r in reports:
        final = r.timeline[-1]
        lines.append(f"\n{'=' * 68}")
        lines.append(f"{r.label} — through {_ym(final.month)}")
        lines.append(
            f"  balance {fmt(final.balance)}   ready-to-pay {fmt(final.set_aside)}   "
            f"uncovered {fmt(r.position.uncovered)}"
        )
        lines.append(
            f"  over-reserved {fmt(r.position.over_reserved)}   "
            f"short-reserved {fmt(r.position.short_reserved)}   "
            f"card-credit {fmt(r.position.card_credit)}   riding {fmt(r.riding)}"
        )
        totals = {leg: sum(cm.legs[leg] for cm in r.timeline) for leg in LEGS}
        lines.append("  lifetime legs: " + "  ".join(f"{leg} {fmt(totals[leg])}" for leg in LEGS))

        if not r.has_payment_category:
            lines.append("  !! this card has NO linked payment envelope — nothing can be assigned")
        if r.first_charge and r.first_reserving and r.first_charge < r.first_reserving:
            lines.append(
                f"  !! first charge {_ym(r.first_charge)} predates first reserving activity "
                f"{_ym(r.first_reserving)} — early debt had nothing reserved against it"
            )
        elif r.first_charge and r.first_reserving is None:
            lines.append(f"  !! charges since {_ym(r.first_charge)} but NO reserving activity ever")

        if r.breach:
            lines.append(
                f"\n  FIRST BREACH: {_ym(r.breach.month)} "
                f"({fmt(r.breach.set_aside_before)} -> {fmt(r.breach.set_aside_after)})"
            )
            for leg, amount in r.breach.ranked_legs:
                lines.append(f"    {leg:>9}: {fmt(amount)}")
        elif final.set_aside >= ZERO:
            lines.append("\n  reserve never went below zero")

        if r.worst and final.set_aside < ZERO:
            lines.append("  worst months (reserve delta):")
            for cm in r.worst:
                drivers = sorted(
                    ((leg, _SIGNS[leg] * cm.legs[leg]) for leg in LEGS), key=lambda t: t[1]
                )
                top = ", ".join(f"{leg} {fmt(a)}" for leg, a in drivers if a < ZERO)
                lines.append(f"    {_ym(cm.month)}: {fmt(cm.reserve_delta)}  ({top})")

        if r.residual_contributors:
            lines.append("  residual by envelope (inflows beyond anything that rode here):")
            for c in r.residual_contributors:
                lines.append(
                    f"    {c.envelope}: {fmt(c.total)} over {c.months} month(s); "
                    f"lifetime charges here {fmt(c.charged_total)} (monthly nets)"
                )
                n, gross = c.charge_rows
                if n:
                    lines.append(f"      charge rows: {n} row(s), gross {fmt(gross)}")
                arrived = "; ".join(
                    f"{_KIND_LABELS.get(kind, kind)}: {n} row(s), net {fmt(net)}"
                    for kind, (n, net) in sorted(c.inflow_kinds.items())
                )
                if arrived:
                    lines.append(f"      inflows arrived as — {arrived}")
        n, net = r.uncategorized
        if n:
            lines.append(
                f"  uncategorized card rows: {n} (net {fmt(net)}) — reserve never sees these"
            )
        n, net = r.system_filed
        if n:
            lines.append(f"  card rows filed to a system (Income) category: {n} (net {fmt(net)})")
        if r.unpaired_legs:
            lines.append(
                f"  unpaired transfer legs on this card: {r.unpaired_legs} — "
                "payments typed as transfers whose partner never linked"
            )
        if r.unclaimed_total != ZERO:
            lines.append(
                f"  unclaimed card rows net {fmt(r.unclaimed_total)} — moves the balance, "
                "touches no envelope (by design)"
            )
        for env, avail in r.shadow_envelopes:
            lines.append(
                f"  possible shadow envelope: {env} holds {fmt(avail)} ≈ the missing reserve — "
                "card payments may have been funded through it"
            )
        if r.ynab:
            month, ours, theirs, compared, divergent = r.ynab
            if divergent:
                lines.append(
                    f"  YNAB: first divergence {_ym(month)} — ours {fmt(ours)} vs "
                    f"YNAB {fmt(theirs)}; {divergent}/{compared} months differ"
                )
            else:
                lines.append(f"  YNAB: agrees in all {compared} compared months")

    lines.append("")
    return "\n".join(lines)


def render_json(
    reports: list[CardReport],
    data: DbData | None,
    fmt,
    scaled: bool,
) -> str:
    def month_row(cm: CardMonth) -> dict:
        return {
            "month": _ym(cm.month),
            **{leg: fmt(cm.legs[leg]) for leg in LEGS},
            "set_aside": fmt(cm.set_aside),
            "balance": fmt(cm.balance),
            "riding": fmt(cm.riding),
        }

    out: dict = {
        "probe": "card_reserve_probe",
        "scaled": scaled,
        "schema_revision": _short_rev(data.alembic_revision) if data else None,
        "import_summary": {
            k: (fmt(Decimal(str(v[1]))) if isinstance(v, tuple) else v)
            for k, v in (data.import_summary if data else {}).items()
        },
        "cards": [],
    }
    for r in reports:
        final = r.timeline[-1]
        # The full series can be ten years long; keep the interesting window
        # and say what was left out rather than truncating silently.
        keep_months = {cm.month for cm in r.worst}
        if r.breach:
            idx = next(i for i, cm in enumerate(r.timeline) if cm.month == r.breach.month)
            keep_months.update(cm.month for cm in r.timeline[max(0, idx - 2) : idx + 3])
        keep_months.update(cm.month for cm in r.timeline[-3:])
        kept = [cm for cm in r.timeline if cm.month in keep_months]
        out["cards"].append(
            {
                "card": r.label,
                "final": month_row(final),
                "position": {
                    "uncovered": fmt(r.position.uncovered),
                    "over_reserved": fmt(r.position.over_reserved),
                    "short_reserved": fmt(r.position.short_reserved),
                    "card_credit": fmt(r.position.card_credit),
                },
                "first_breach": (
                    {
                        "month": _ym(r.breach.month),
                        "before": fmt(r.breach.set_aside_before),
                        "after": fmt(r.breach.set_aside_after),
                        "legs": {leg: fmt(a) for leg, a in r.breach.ranked_legs},
                    }
                    if r.breach
                    else None
                ),
                "months": [month_row(cm) for cm in kept],
                "months_elided": len(r.timeline) - len(kept),
                "residual_by_envelope": [
                    {
                        "envelope": c.envelope,
                        "months": c.months,
                        "total": fmt(c.total),
                        "charged_lifetime": fmt(c.charged_total),
                        "charge_rows": {"rows": c.charge_rows[0], "gross": fmt(c.charge_rows[1])},
                        "inflows": {
                            kind: {"rows": n, "net": fmt(net)}
                            for kind, (n, net) in sorted(c.inflow_kinds.items())
                        },
                        "monthly": [
                            {"month": _ym(m), "amount": fmt(a)} for m, a in c.monthly.items()
                        ],
                    }
                    for c in r.residual_contributors
                ],
                "uncategorized_rows": {
                    "count": r.uncategorized[0],
                    "net": fmt(r.uncategorized[1]),
                },
                "system_filed_rows": {
                    "count": r.system_filed[0],
                    "net": fmt(r.system_filed[1]),
                },
                "unpaired_transfer_legs": r.unpaired_legs,
                "unclaimed_net": fmt(r.unclaimed_total),
                "first_charge": _ym(r.first_charge) if r.first_charge else None,
                "first_reserving": _ym(r.first_reserving) if r.first_reserving else None,
                "has_payment_category": r.has_payment_category,
                "shadow_envelopes": [
                    {"envelope": env, "available": fmt(avail)} for env, avail in r.shadow_envelopes
                ],
                "ynab": (
                    {
                        "first_divergence": _ym(r.ynab[0]),
                        "ours": fmt(r.ynab[1]),
                        "theirs": fmt(r.ynab[2]),
                        "months_compared": r.ynab[3],
                        "months_divergent": r.ynab[4],
                    }
                    if r.ynab
                    else None
                ),
            }
        )
    return json.dumps(out, indent=2)


# ─── Entry point ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--budget", help="budget id when the instance has several")
    ap.add_argument("--out", default="/tmp/card_reserve_report", help="output prefix")
    ap.add_argument("--scale", type=Decimal, default=None, help="rescale every amount")
    ap.add_argument("--key", help="write the pseudonym key here (LOCAL ONLY — never send)")
    ap.add_argument("--ynab-zip", help="YNAB export zip for the oracle overlay")
    args = ap.parse_args(argv)

    database_url = os.environ.get("DATABASE_URL")
    if database_url is None and args.ynab_zip is None:
        print(
            "no DATABASE_URL in the environment and no --ynab-zip; nothing to read", file=sys.stderr
        )
        return 2

    ynab_ccp = None
    ynab_unreadable = None
    ynab_source = None
    if args.ynab_zip:
        ynab_ccp, ynab_unreadable = read_ynab_ccp_available(args.ynab_zip)
        ynab_source = "the export zip"

    names = Pseudonyms()
    scale = args.scale if args.scale is not None else Decimal("1")
    fmt = money_formatter(scale)

    data: DbData | None = None
    reports: list[CardReport] = []
    if database_url is not None:
        data = asyncio.run(read_db(database_url, args.budget))
        if ynab_ccp is None and data.ynab_ccp_from_import:
            ynab_ccp = data.ynab_ccp_from_import
            ynab_source = "the plan history persisted with the import summary"
        reports = analyze(data, names, ynab_ccp)
    elif ynab_ccp is not None:
        # Zip-only mode: report YNAB's own CCP series and its negative months.
        for card_name in sorted(ynab_ccp):
            label = names.get("card", card_name)
            series = ynab_ccp[card_name]
            timeline = [
                CardMonth(
                    month=m,
                    legs={leg: ZERO for leg in LEGS},
                    set_aside=series[m],
                    balance=ZERO,
                    riding=ZERO,
                )
                for m in sorted(series)
            ]
            reports.append(
                CardReport(
                    label=label,
                    timeline=timeline,
                    breach=first_breach(timeline),
                    worst=[],
                    position=card_position(timeline[-1].set_aside, ZERO),
                    riding=ZERO,
                    residual_contributors=[],
                    uncategorized=(0, ZERO),
                    system_filed=(0, ZERO),
                    unpaired_legs=0,
                    unclaimed_total=ZERO,
                    first_charge=None,
                    first_reserving=None,
                    has_payment_category=True,
                    shadow_envelopes=[],
                )
            )

    text_report = render_text(
        reports,
        data,
        fmt,
        scaled=args.scale is not None,
        ynab_unreadable=ynab_unreadable,
        ynab_empty=ynab_ccp is not None and not ynab_ccp,
        ynab_source=ynab_source if ynab_ccp else None,
    )
    json_report = render_json(reports, data, fmt, scaled=args.scale is not None)

    deny = names.deny_tokens()
    assert_clean(text_report, deny)
    assert_clean(json_report, deny)

    txt_path = args.out + ".txt"
    json_path = args.out + ".json"
    with open(txt_path, "w") as fh:
        fh.write(text_report)
    with open(json_path, "w") as fh:
        fh.write(json_report)
    if args.key:
        with open(args.key, "w") as fh:
            fh.write("PSEUDONYM KEY — for your eyes only. NEVER send this file.\n")
            fh.write("\n".join(names.key_lines()) + "\n")

    print(text_report)
    print(f"wrote {txt_path} and {json_path}", file=sys.stderr)
    if args.key:
        print(f"wrote pseudonym key to {args.key} — do NOT send that file", file=sys.stderr)
    if args.scale is None:
        print(
            "note: amounts are real. Re-run with --scale <factor> to rescale them "
            "before sharing, and keep the factor to yourself.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
