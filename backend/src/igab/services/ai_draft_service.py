"""The single mapping from AI-extracted JSON to a real transaction draft.

Used by the receipt worker and the NL-parse endpoint (and any future AI entry
source). parse_extraction() is pure so the amount/date/category edge cases can
be tested exhaustively; create_transaction() delegates to TransactionService so
every existing invariant (budget scoping, payee resolution precedence, payee
auto-categorization) is reused rather than reimplemented.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast

from igab.db.models import Transaction
from igab.domain.exceptions import InvariantViolation
from igab.services.category_matching import Candidate, canonical_label, match_category
from igab.services.transaction_service import TransactionCreate, TransactionService

_CENT = Decimal("0.01")
# Tolerant fallbacks for models that ignore the YYYY-MM-DD instruction
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d")


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
    # Only present when every line resolved cleanly and sums matched; never
    # auto-applied — offered to the user in the review modal.
    suggested_split: list[SplitLine] | None
    raw: dict = field(default_factory=dict)


def _parse_amount(value: object) -> Decimal:
    if value is None:
        raise InvariantViolation("AI extraction returned no amount")
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        raise InvariantViolation(f"AI extraction returned a non-numeric amount: {value!r}")
    try:
        amount = Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise InvariantViolation(f"AI extraction returned a non-numeric amount: {value!r}")
    if amount == 0:
        raise InvariantViolation("AI extraction returned a zero amount")
    return amount


def _parse_date(value: object, client_today: datetime.date) -> datetime.date:
    """Best-effort date parse; receipts are past events, so anything
    unparseable or in the future falls back to today rather than failing
    the whole extraction."""
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
    if parsed is None or parsed > client_today + datetime.timedelta(days=1):
        return client_today
    return parsed


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
    """Validate a suggested split. Offerable only when every line's category
    resolves against the budget and the lines sum to the total (within one
    cent). Anything else returns None — the raw line_items stay in the job
    result for display, but we never offer a split we can't apply."""
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
        try:
            line_amount = Decimal(str(entry.get("amount"))).quantize(_CENT, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return None
        if line_amount == 0:
            return None
        # Model amounts are positive; carry the draft's sign
        signed = -line_amount.copy_abs() if total < 0 else line_amount.copy_abs()
        running += signed
        lines.append(SplitLine(category_name=canonical_label(matched, candidates), amount=signed))
    if (running - total).copy_abs() > _CENT:
        return None
    return lines


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

    matched = match_category(_clean_str(raw.get("category")), candidates)
    category_name = canonical_label(matched, candidates) if matched is not None else None

    try:
        confidence = min(max(float(raw.get("confidence", 0.0)), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.0

    suggested_split = None
    if kind == "receipt":
        suggested_split = _parse_split(raw.get("suggested_split"), signed, candidates)

    return AIDraft(
        payee_name=_clean_str(raw.get("payee")),
        amount=signed,
        date=_parse_date(raw.get("date"), client_today),
        category_name=category_name,
        memo=_clean_str(raw.get("memo")),
        confidence=confidence,
        suggested_split=suggested_split,
        raw=raw,
    )


class AIDraftService:
    def __init__(self, transaction_service: TransactionService) -> None:
        self.transactions = transaction_service

    async def resolve_category(self, budget_id: uuid.UUID, name: str | None) -> uuid.UUID | None:
        """Tolerant name match against the budget's live categories —
        decoration-stripping and group qualification via category_matching.
        No match ⇒ None (uncategorized), letting the existing payee
        auto-categorization in TransactionService.create() apply."""
        if not name:
            return None
        pairs = await self.transactions.category_repo.get_all_with_group_names(budget_id)
        matched = match_category(name, [(cat.name, group) for cat, group in pairs])
        return pairs[matched][0].id if matched is not None else None

    async def create_transaction(
        self,
        budget_id: uuid.UUID,
        account_id: uuid.UUID,
        draft: AIDraft,
        *,
        created_via: str,
    ) -> Transaction:
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
        )
        return await self.transactions.create(budget_id, data)
