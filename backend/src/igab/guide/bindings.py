"""Turning stored binding rows into one answer per concept.

Detection produces a guess. This decides how much of that guess survives what
the user has said. Kept free of database access so the precedence rules can be
tested directly — they are the part that decides whether someone's roadmap
tells them the truth.

Precedence, highest first:

``dismissed``  the concept is not tracked. Nothing else about it matters, and
               no claim is made either way. Deliberately beats the rest: the
               user asked to stop hearing about it.
``manual``     these entities are what counts. Detection stops guessing.
``external``   adds a self-reported amount on top. Additive rather than
               exclusive, because half here and half at another bank is the
               ordinary arrangement, not an edge case.
``answer``     a stored yes/no for concepts nothing in a budget can answer.
``auto``       no rows at all — detection speaks for itself.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol
from uuid import UUID


class BindingRow(Protocol):
    """The shape this module needs — satisfied by db.models.GuideBinding."""

    concept_key: str
    mode: str
    entity_type: str | None
    entity_id: UUID | None
    answer: bool | None
    amount: Decimal | None
    as_of: date | None
    note: str | None


@dataclass(frozen=True)
class Resolution:
    """How one concept should be answered."""

    concept_key: str
    #: 'auto' | 'manual' | 'external' | 'manual+external' | 'dismissed' | 'answer'
    source: str
    #: Entities the user pointed at, by type. Empty under 'auto'.
    entities: dict[str, tuple[UUID, ...]] = field(default_factory=dict)
    #: Self-reported total held outside IGAB. None means either no external
    #: row, or one with no figure — "I have this covered" without a number,
    #: which is a complete answer and must not be read as zero.
    external_amount: Decimal | None = None
    external_declared: bool = False
    external_as_of: date | None = None
    note: str | None = None
    answer: bool | None = None

    @property
    def tracked(self) -> bool:
        """False when the user asked us to leave this concept alone."""
        return self.source != "dismissed"

    @property
    def uses_detection(self) -> bool:
        """Whether detection should still run and be counted."""
        return self.source in ("auto", "external")


def resolve(concept_key: str, rows: list[BindingRow]) -> Resolution:
    """Fold every stored row for one concept into a single answer."""
    mine = [r for r in rows if r.concept_key == concept_key]
    if not mine:
        return Resolution(concept_key=concept_key, source="auto")

    if any(r.mode == "dismissed" for r in mine):
        # One dismissal wins even alongside other rows: the rows may be
        # leftovers from before, and re-reading them would resurrect a claim
        # the user switched off.
        note = next((r.note for r in mine if r.mode == "dismissed" and r.note), None)
        return Resolution(concept_key=concept_key, source="dismissed", note=note)

    answered = next((r for r in mine if r.mode == "answer"), None)
    if answered is not None and answered.answer is not None:
        return Resolution(
            concept_key=concept_key,
            source="answer",
            answer=answered.answer,
            note=answered.note,
        )

    entities: dict[str, list[UUID]] = {}
    for r in mine:
        if r.mode != "manual" or r.entity_type is None or r.entity_id is None:
            continue
        entities.setdefault(r.entity_type, []).append(r.entity_id)

    external_rows = [r for r in mine if r.mode == "external"]
    amounts = [r.amount for r in external_rows if r.amount is not None]
    external_amount = sum(amounts, Decimal("0")) if amounts else None
    # A row with no figure still counts as a declaration — see the docstring
    # on Resolution.external_amount.
    external_declared = bool(external_rows)
    as_of = max((r.as_of for r in external_rows if r.as_of is not None), default=None)
    ext_note = next((r.note for r in external_rows if r.note), None)

    has_manual = bool(entities)
    if has_manual and external_declared:
        source = "manual+external"
    elif has_manual:
        source = "manual"
    elif external_declared:
        source = "external"
    else:
        # Rows exist but none of them says anything usable — a stale 'answer'
        # row with a null answer, say. Fall back rather than invent.
        source = "auto"

    return Resolution(
        concept_key=concept_key,
        source=source,
        entities={k: tuple(v) for k, v in entities.items()},
        external_amount=external_amount,
        external_declared=external_declared,
        external_as_of=as_of,
        note=ext_note,
    )


def resolve_all(concept_keys: list[str], rows: list[BindingRow]) -> dict[str, Resolution]:
    return {key: resolve(key, rows) for key in concept_keys}
