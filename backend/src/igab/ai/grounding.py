"""Checking that the figures in an answer came from the budget.

The system prompt already tells the model never to invent a figure. That is a
request, not a mechanism — and this repo's own rule is that a comment is not a
mechanism. A 7-8B model asked for "roughly what did I spend" will happily round
$1,182.40 to "about $1,200", and a worse one will produce a number it never saw
at all. Neither is visible in prose.

So every money figure in an answer is matched against the numbers the tools
actually returned, and the answer carries the result. Three outcomes:

- **grounded** — the figure appears in a tool result.
- **derived** — it is the sum or difference of two grounded figures, which is
  legitimate arithmetic ("Groceries $120 and Dining $45 come to $165") and must
  not be reported as invention, or the check cries wolf and stops being read.
- **unsupported** — neither. Shown to the user, not hidden and not blocked:
  the model may be right and the check may be narrow, but the user is the one
  who should decide that.

Pure — no session, no model, no clock — so every rule here is a one-line test
rather than something you reproduce by asking a local model nicely.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

#: Money in prose: an explicit currency mark, or a bare number with cents.
#: Deliberately narrow. A count ("3 transactions") or a year ("2026") is not
#: what this protects — a wrong dollar figure is, and widening the net to
#: catch every integer would flag dates and ordinals until nobody read it.
_MONEY = re.compile(
    r"""
    (?<![\w.])                # not mid-identifier
    (?:
        [$£€]\s?(?P<sym>\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)
      | (?P<bare>\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})
    )
    (?![\w%])                 # 12.50% is a rate, not an amount
    """,
    re.VERBOSE,
)

#: How close counts as the same figure. Two cents of slack absorbs the
#: half-cent rounding a report does on its way to a percentage; more would
#: start calling genuinely different amounts equal.
TOLERANCE = Decimal("0.02")

#: Ceiling on the grounded set used for the derived (a±b) search. The pass is
#: quadratic, and a tool result with thousands of numbers would spend real time
#: proving something nobody asked about.
_MAX_PAIRWISE = 250


@dataclass(frozen=True)
class Figure:
    """One money amount as the answer wrote it."""

    text: str
    value: Decimal


@dataclass
class GroundingReport:
    """What the figures in an answer are backed by."""

    #: Every money figure found in the answer.
    figures: list[Figure] = field(default_factory=list)
    grounded: list[Figure] = field(default_factory=list)
    derived: list[Figure] = field(default_factory=list)
    unsupported: list[Figure] = field(default_factory=list)
    #: How many lookups the answer had available to draw on.
    lookups: int = 0

    @property
    def checked(self) -> bool:
        """Whether there was anything to check."""
        return bool(self.figures)

    @property
    def clean(self) -> bool:
        """Every figure traced back to the budget."""
        return self.checked and not self.unsupported

    def as_record(self) -> dict:
        """The stored and streamed shape."""
        return {
            "figures": len(self.figures),
            "grounded": len(self.grounded),
            "derived": len(self.derived),
            "unsupported": [f.text for f in self.unsupported],
            "lookups": self.lookups,
        }


def extract_figures(text: str) -> list[Figure]:
    """Every money amount in a piece of prose, in order."""
    figures: list[Figure] = []
    for match in _MONEY.finditer(text or ""):
        raw = match.group("sym") or match.group("bare")
        try:
            figures.append(Figure(text=match.group(0).strip(), value=Decimal(raw.replace(",", ""))))
        except InvalidOperation:
            continue
    return figures


def collect_numbers(value: Any, into: set[Decimal] | None = None) -> set[Decimal]:
    """Every number anywhere in a tool result, as absolute values.

    Absolute because the ledger stores spending negative and every surface in
    this app shows it positive; a model quoting "$120" from a -120 row is
    quoting the number it was given.
    """
    found = into if into is not None else set()
    if isinstance(value, bool):
        return found
    if isinstance(value, int | float | Decimal):
        try:
            found.add(abs(Decimal(str(value))))
        except InvalidOperation:
            pass
        return found
    if isinstance(value, str):
        # Numbers inside a string a tool returned — a note, a formatted total.
        for match in re.finditer(r"-?\d+(?:\.\d+)?", value):
            try:
                found.add(abs(Decimal(match.group(0))))
            except InvalidOperation:
                continue
        return found
    if isinstance(value, dict):
        for item in value.values():
            collect_numbers(item, found)
        return found
    if isinstance(value, list | tuple):
        for item in value:
            collect_numbers(item, found)
    return found


def _near(value: Decimal, candidates: set[Decimal]) -> bool:
    if value in candidates:
        return True
    return any(abs(value - candidate) <= TOLERANCE for candidate in candidates)


def _is_derived(value: Decimal, grounded: list[Decimal]) -> bool:
    """Whether a figure is the sum or difference of two grounded ones.

    Adding two envelopes together is the most ordinary thing an answer does,
    and reporting it as invention would make the whole check noise.
    """
    for i, a in enumerate(grounded):
        for b in grounded[i:]:
            if abs(value - (a + b)) <= TOLERANCE or abs(value - abs(a - b)) <= TOLERANCE:
                return True
    return False


def check(answer: str, tool_results: list[Any], *, lookups: int | None = None) -> GroundingReport:
    """Match every money figure in `answer` against what the tools returned."""
    figures = extract_figures(answer)
    report = GroundingReport(
        figures=figures,
        lookups=len(tool_results) if lookups is None else lookups,
    )
    if not figures:
        return report

    known: set[Decimal] = set()
    for result in tool_results:
        collect_numbers(result, known)

    pairwise = sorted(known)[:_MAX_PAIRWISE]
    for figure in figures:
        if _near(abs(figure.value), known):
            report.grounded.append(figure)
        elif _is_derived(abs(figure.value), pairwise):
            report.derived.append(figure)
        else:
            report.unsupported.append(figure)
    return report
