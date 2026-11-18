"""The single mapping from AI-extracted JSON to a real transaction draft.

Used by the AI job worker for receipts and descriptions alike, and by placing
a waiting one (and any future AI entry source). parse_extraction() is pure so
the amount/date/category edge cases can be tested exhaustively;
create_transaction() delegates to TransactionService so every existing
invariant (budget scoping, payee resolution precedence, payee
auto-categorization) is reused rather than reimplemented.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, cast

from igab.db.models import Transaction
from igab.domain.card_endings import card_last4
from igab.domain.exceptions import InvariantViolation
from igab.domain.money import model_cents
from igab.domain.receipt_checks import (
    MODEL_ROUNDING_SLACK,
    ReceiptCheck,
    capped_confidence,
    checked_receipt_date,
    line_items_mismatch,
    looping_items,
    named_for_payee,
    past_tomorrow,
    summary_line,
    tender_disagrees,
)
from igab.domain.splits import split_balances
from igab.services.category_matching import Candidate, canonical_label, match_category
from igab.services.transaction_service import SplitSpec, TransactionCreate, TransactionService

# Tolerant fallbacks for models that ignore the YYYY-MM-DD instruction
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d")

# The replies parse_extraction reads, as JSON schemas for Ollama's `format`.
# `format: "json"` only promised *some* object: {"merchant": …, "amount": …}
# parsed, then failed as "no amount". A schema makes the grammar spell the
# keys this module reads, and every key is required, so a prompt override
# saved before a field existed still gets it (null when the receipt has none).
#
# The prompt describes the same fields in prose — irreducibly, since the
# model reads the prompt and the grammar reads this. test_ai_reply_schema
# holds the two together, and holds this to what parse_extraction reads.
_TEXT_OR_NULL = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NUMBER_OR_NULL = {"anyOf": [{"type": "number"}, {"type": "null"}]}

#: The grammar's bound on both arrays. Past any real receipt (a full
#: warehouse-club shop is ~60 lines), so it only ever ends a loop.
MAX_RECEIPT_ITEMS = 80
#: Set on a receipt's raw extraction when the reply was cut short and only
#: the members before the cut were kept (`AIService.extract_receipt`). It is
#: stored with the extraction, so a later re-read of the same job reaches the
#: same verdict.
RAW_CUT_SHORT = "cut_short"

# Every scalar comes before the arrays, and the grammar writes members in
# schema order: a reply cut short in its line items has already given payee,
# total and date.
RECEIPT_REPLY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "payee": _TEXT_OR_NULL,
        "total": {"type": "number"},
        "tender_amount": _NUMBER_OR_NULL,
        "date": _TEXT_OR_NULL,
        "category": _TEXT_OR_NULL,
        "reason": _TEXT_OR_NULL,
        "confidence": {"type": "number"},
        "memo": _TEXT_OR_NULL,
        "card_last4": _TEXT_OR_NULL,
        "line_items": {
            "type": "array",
            "maxItems": MAX_RECEIPT_ITEMS,
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "category": _TEXT_OR_NULL,
                },
                "required": ["description", "amount", "category"],
            },
        },
        "suggested_split": {
            "type": "array",
            "maxItems": MAX_RECEIPT_ITEMS,
            "items": {
                "type": "object",
                "properties": {"category": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["category", "amount"],
            },
        },
    },
    "required": [
        "payee",
        "total",
        "tender_amount",
        "date",
        "category",
        "reason",
        "confidence",
        "memo",
        "card_last4",
        "line_items",
        "suggested_split",
    ],
}

NL_REPLY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "payee": _TEXT_OR_NULL,
        "amount": {"type": "number"},
        "direction": {"type": "string", "enum": ["outflow", "inflow"]},
        "date": _TEXT_OR_NULL,
        "category": _TEXT_OR_NULL,
        "memo": _TEXT_OR_NULL,
        "confidence": {"type": "number"},
    },
    "required": ["payee", "amount", "direction", "date", "category", "memo", "confidence"],
}


@dataclass
class SplitLine:
    category_name: str
    amount: Decimal  # signed like the draft amount


@dataclass
class AIDraft:
    payee_name: str | None
    amount: Decimal  # signed, outflow-negative
    date: datetime.date
    category_name: str | None
    memo: str | None
    confidence: float
    # Only present when every line resolved cleanly and sums matched. Filed
    # as the row's split when the scan lands (`AIDraftService.split_lines`),
    # still unapproved, so the review is where a person checks it.
    suggested_split: list[SplitLine] | None
    raw: dict = field(default_factory=dict)
    #: The category the model NAMED when it named one this budget could not
    #: resolve to exactly one category (no such name, or several). Distinct
    #: from "the model had no opinion": that falls through to payee history,
    #: this must not — history filed a garden receipt in an unrelated
    #: envelope while the model's reason, shown beside it, named Garden.
    category_unresolved: str | None = None
    #: The last four digits of the card that paid, when the receipt prints
    #: them — which account owns them is `card_ending_owner`'s question.
    card_last4: str | None = None
    #: The fields the read failed a plausibility check on, for the review to
    #: point at. Any check has already capped `confidence`.
    checks: list[ReceiptCheck] = field(default_factory=list)
    #: The date the receipt was read as when it fell outside the window and
    #: `date` is today instead.
    date_read: datetime.date | None = None
    #: The payment line's amount, when it disagrees with the total.
    tender_amount: Decimal | None = None
    #: What the line items add up to, when that disagrees with the total.
    line_items_total: Decimal | None = None
    #: The category the model picked, when the draft carries another one
    #: instead — and where the other came from: "items" (most of the line
    #: items' dollars) or "history" (what this payee is usually filed to).
    category_model: str | None = None
    category_from: str | None = None
    #: The model's category carries the store's own name and the line items
    #: had no say: payee history is asked before it is filed
    #: (`AIDraftService.second_opinion`).
    category_suspect: bool = False


def _parse_amount(value: object) -> Decimal:
    if value is None:
        raise InvariantViolation("AI extraction returned no amount")
    amount = model_cents(value)
    if amount is None:
        raise InvariantViolation(f"AI extraction returned a non-numeric amount: {value!r}")
    if amount == 0:
        raise InvariantViolation("AI extraction returned a zero amount")
    return amount


def _parse_date(value: object) -> datetime.date | None:
    """Best-effort date parse; None when the model gave nothing readable.
    Unreadable never fails the whole extraction — the caller falls back to
    today."""
    parsed: datetime.date | None = None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parsed = datetime.date.fromisoformat(text)
            except ValueError:
                parsed = None
    return parsed


def _description_date(parsed: datetime.date | None, client_today: datetime.date) -> datetime.date:
    """A description's date: what the person said, or today. Not held to a
    receipt's window — a person typing a date long past means it — but a
    future one is still a misread."""
    if parsed is None or past_tomorrow(parsed, client_today):
        return client_today
    return parsed


def _line_amounts(raw_items: object) -> list[Decimal]:
    """The line items' amounts, discounts negative as the model wrote them.
    Empty when there are none or any one is unreadable: a partial sum
    would flag a total that is right."""
    if not isinstance(raw_items, list):
        return []
    amounts: list[Decimal] = []
    for item in raw_items:
        amount = (
            model_cents(cast(dict[str, Any], item).get("amount"))
            if isinstance(item, dict)
            else None
        )
        if amount is None:
            return []
        amounts.append(amount)
    return amounts


def _clean_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_candidates(
    category_names: Collection[str | tuple[str, str | None]] | None,
) -> list[Candidate]:
    """Callers pass either bare names or (name, group) pairs; group names
    enable disambiguation when the same category name exists in several
    groups."""
    candidates: list[Candidate] = []
    for entry in category_names or ():
        if isinstance(entry, str):
            candidates.append((entry, None))
        else:
            name, group = entry
            candidates.append((name, group))
    return candidates


def _parse_split(
    raw_split: object, total: Decimal, candidates: Sequence[Candidate]
) -> list[SplitLine] | None:
    """Validate a suggested split.

    Offerable only when every line's category resolves against the budget and
    the lines sum to the total within `MODEL_ROUNDING_SLACK`. That is slack
    for the MODEL, not for the ledger, whose invariant has no tolerance (see
    domain/splits.py). Anything else returns None — the raw line_items stay
    in the job result for display, but we never offer a split we can't
    apply.

    A surviving split whose lines are a cent out is repaired here rather than
    passed along: the residual is absorbed into the last line so the result
    sums exactly. Offering a split that TransactionService would then reject
    is a button that lies, and offering one it would *accept* on a tolerance
    is a row IntegrityService flags forever."""
    if not isinstance(raw_split, list) or len(raw_split) < 2:
        return None
    lines: list[SplitLine] = []
    running = Decimal("0")
    for item in raw_split:
        if not isinstance(item, dict):
            return None
        entry = cast(dict[str, Any], item)
        name = _clean_str(entry.get("category"))
        matched = match_category(name, candidates)
        if matched is None:
            return None
        line_amount = model_cents(entry.get("amount"))
        if line_amount is None or line_amount == 0:
            return None
        # Model amounts are positive; carry the draft's sign
        signed = -line_amount.copy_abs() if total < 0 else line_amount.copy_abs()
        running += signed
        lines.append(SplitLine(category_name=canonical_label(matched, candidates), amount=signed))
    if (running - total).copy_abs() > MODEL_ROUNDING_SLACK:
        return None

    # Absorb the model's rounding residual into the last line, then hold the
    # result to the ledger's exact rule.
    residual = total - running
    if residual != 0:
        lines[-1] = SplitLine(
            category_name=lines[-1].category_name, amount=lines[-1].amount + residual
        )
    if not split_balances(total, [line.amount for line in lines]):
        return None
    return lines


def _items_vote(items: object, candidates: Sequence[Candidate]) -> int | None:
    """The category most of the line items' dollars name — a majority, or
    None. The header category is written before the items are read, so the
    items are the better-informed of the two."""
    if not isinstance(items, list):
        return None
    weights: dict[int, Decimal] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, Any], item)
        index = match_category(_clean_str(entry.get("category")), candidates)
        amount = model_cents(entry.get("amount"))
        if index is None or amount is None:
            continue
        weights[index] = weights.get(index, Decimal("0")) + amount.copy_abs()
    if not weights:
        return None
    best = max(weights, key=lambda index: weights[index])
    return best if weights[best] * 2 > sum(weights.values()) else None


def parse_extraction(
    raw: dict,
    *,
    kind: str,
    client_today: datetime.date,
    category_names: Collection[str | tuple[str, str | None]] | None = None,
) -> AIDraft:
    """Map validated-JSON model output to a draft.

    kind='receipt': `total` is the amount; positive totals are purchases
    (outflow ⇒ negated), negative totals are refunds (inflow).
    kind='nl_parse': `amount` + `direction` (outflow|inflow).

    category_names entries may be bare names or (name, group) pairs; matching
    is tolerant (see category_matching) and the draft carries the real
    category's canonical label, not the model's spelling of it.
    """
    candidates = _as_candidates(category_names)

    if kind == "receipt":
        amount = _parse_amount(raw.get("total"))
        signed = -amount if amount > 0 else amount.copy_abs()
    elif kind == "nl_parse":
        amount = _parse_amount(raw.get("amount")).copy_abs()
        direction = _clean_str(raw.get("direction")) or "outflow"
        signed = amount if direction.lower() == "inflow" else -amount
    else:
        raise InvariantViolation(f"Unknown AI draft kind: {kind}")

    named = _clean_str(raw.get("category"))
    matched = match_category(named, candidates)
    category_name = canonical_label(matched, candidates) if matched is not None else None

    try:
        confidence = min(max(float(raw.get("confidence", 0.0)), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.0

    draft = AIDraft(
        payee_name=_clean_str(raw.get("payee")),
        amount=signed,
        date=_description_date(_parse_date(raw.get("date")), client_today),
        category_name=category_name,
        memo=_clean_str(raw.get("memo")),
        confidence=confidence,
        suggested_split=None,
        raw=raw,
        category_unresolved=named if named and category_name is None else None,
    )
    if kind == "receipt":
        _check_receipt(draft, amount, client_today, candidates)
        if matched is not None:
            _second_guess_category(draft, matched, candidates)
    return draft


def _check_receipt(
    draft: AIDraft, amount: Decimal, client_today: datetime.date, candidates: Sequence[Candidate]
) -> None:
    """What only a receipt has, written onto its draft: the split when the
    items can carry one, the card ending, and the plausibility checks —
    each failed one named, and the confidence capped for any."""
    raw = draft.raw
    items = raw.get("line_items")
    itemized = not raw.get(RAW_CUT_SHORT) and not (
        isinstance(items, list) and (looping_items(items) or summary_line(items, amount))
    )
    checks: list[ReceiptCheck] = []
    dated = checked_receipt_date(_parse_date(raw.get("date")), client_today)
    draft.date, draft.date_read = dated.date, dated.read_as
    if draft.date_read is not None:
        checks.append(ReceiptCheck.DATE)
    tender_read = model_cents(raw.get("tender_amount"))
    if tender_disagrees(amount, tender_read):
        draft.tender_amount = tender_read
    if itemized:
        draft.suggested_split = _parse_split(raw.get("suggested_split"), draft.amount, candidates)
        draft.line_items_total = line_items_mismatch(amount, _line_amounts(items))
    if draft.tender_amount is not None or draft.line_items_total is not None:
        checks.append(ReceiptCheck.AMOUNT)
    if not itemized:
        checks.append(ReceiptCheck.ITEMS)
    draft.card_last4 = card_last4(raw.get("card_last4"))
    draft.checks = checks
    draft.confidence = capped_confidence(draft.confidence, checks)


def _second_guess_category(draft: AIDraft, matched: int, candidates: Sequence[Candidate]) -> None:
    """A category with the store's own name was matched on the name. The
    line items decide when they can — even those of a cut-short read;
    otherwise the draft is marked for payee history to be asked
    (`AIDraftService.second_opinion`)."""
    if not named_for_payee(candidates[matched][0], draft.payee_name):
        return
    vote = _items_vote(draft.raw.get("line_items"), candidates)
    if vote is None:
        draft.category_suspect = True
    elif vote != matched:
        draft.category_model, draft.category_from = draft.category_name, "items"
        draft.category_name = canonical_label(vote, candidates)


def draft_result_json(draft: AIDraft) -> dict:
    """What an AI job records about the draft it produced — the one shape the
    worker stores in `job.result` for a receipt and a description alike."""
    return {
        "extraction": draft.raw,
        "draft": {
            "payee": draft.payee_name,
            "amount": str(draft.amount),
            "date": draft.date.isoformat(),
            "category": draft.category_name,
            "category_unresolved": draft.category_unresolved,
            # Set when the draft's category is not the model's pick: a
            # category named after the store, overruled by the line items
            # or by what this payee is usually filed to.
            "category_model": draft.category_model,
            "category_from": draft.category_from,
            "card_last4": draft.card_last4,
            "memo": draft.memo,
            "confidence": draft.confidence,
            # Which fields failed a plausibility check, and what was read
            # for each — the review names them (AIReviewBanner).
            "checks": [check.value for check in draft.checks],
            "date_read": draft.date_read.isoformat() if draft.date_read else None,
            "tender_amount": str(draft.tender_amount) if draft.tender_amount is not None else None,
            "line_items_total": (
                str(draft.line_items_total) if draft.line_items_total is not None else None
            ),
        },
        "suggested_split": (
            [{"category": s.category_name, "amount": str(s.amount)} for s in draft.suggested_split]
            if draft.suggested_split
            else None
        ),
    }


class AIDraftService:
    def __init__(self, transaction_service: TransactionService) -> None:
        self.transactions = transaction_service

    async def resolve_category(self, budget_id: uuid.UUID, name: str | None) -> uuid.UUID | None:
        """Tolerant name match against the categories a row may be filed to
        (`get_fileable_with_group_names`, the list the label was made from) —
        decoration-stripping and group qualification via category_matching.
        No match ⇒ None (uncategorized), letting the existing payee
        auto-categorization in TransactionService.create() apply."""
        if not name:
            return None
        pairs = await self.transactions.category_repo.get_fileable_with_group_names(budget_id)
        matched = match_category(name, [(cat.name, group) for cat, group in pairs])
        return pairs[matched][0].id if matched is not None else None

    async def second_opinion(self, budget_id: uuid.UUID, draft: AIDraft) -> AIDraft:
        """Payee history's say over a category that carries the store's name
        and that the line items could not confirm (`category_suspect`).

        Asked of `guess_category_for` — the one answer for "what is this
        payee usually filed to". The model's pick stands when the payee is
        new, when history has no answer, or when history agrees."""
        if not draft.category_suspect or not draft.payee_name:
            return draft
        payee = await self.transactions.find_payee(budget_id, draft.payee_name)
        if payee is None:
            return draft
        usual = await self.transactions.guess_category_for(budget_id, payee.id, draft.amount)
        if usual is None:
            return draft
        pairs = await self.transactions.category_repo.get_fileable_with_group_names(budget_id)
        candidates = [(cat.name, group) for cat, group in pairs]
        index = next((i for i, (cat, _) in enumerate(pairs) if cat.id == usual), None)
        if index is None or index == match_category(draft.category_name, candidates):
            return draft
        return replace(
            draft,
            category_name=canonical_label(index, candidates),
            category_model=draft.category_name,
            category_from="history",
        )

    async def split_lines(self, budget_id: uuid.UUID, draft: AIDraft) -> list[SplitSpec] | None:
        """The draft's split as lines to file, or None when there is none to
        file: no split, or a line whose category no longer resolves — renamed
        or archived between the read and now. A split is filed whole or not
        at all; half of one would be a row the receipt never described.

        `_parse_split` already held the lines to the ledger's exact sum, so
        `create_split` / `convert_to_split` accept them as they are."""
        if not draft.suggested_split:
            return None
        lines: list[SplitSpec] = []
        for line in draft.suggested_split:
            category_id = await self.resolve_category(budget_id, line.category_name)
            if category_id is None:
                return None
            lines.append(SplitSpec(amount=line.amount, category_id=category_id))
        return lines

    async def create_transaction(
        self,
        budget_id: uuid.UUID,
        account_id: uuid.UUID,
        draft: AIDraft,
        *,
        created_via: str,
    ) -> Transaction:
        lines = await self.split_lines(budget_id, draft)
        if lines is not None:
            header = TransactionCreate(
                account_id=account_id,
                date=draft.date,
                amount=draft.amount,
                payee_name=draft.payee_name,
                memo=draft.memo,
                approved=False,
                created_via=created_via,
                auto_categorize=False,
            )
            return await self.transactions.create_split(
                budget_id,
                header,
                [
                    TransactionCreate(
                        account_id=account_id,
                        date=draft.date,
                        amount=line.amount,
                        category_id=line.category_id,
                    )
                    for line in lines
                ],
            )
        category_id = await self.resolve_category(budget_id, draft.category_name)
        data = TransactionCreate(
            account_id=account_id,
            date=draft.date,
            amount=draft.amount,
            payee_name=draft.payee_name,
            category_id=category_id,
            memo=draft.memo,
            approved=False,
            created_via=created_via,
            # Payee history is for a draft with no opinion. A category the
            # model named and we failed to resolve is an opinion; guessing
            # over it reads as the AI mis-filing.
            auto_categorize=draft.category_unresolved is None,
        )
        return await self.transactions.create(budget_id, data)
