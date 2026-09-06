"""What a monthly debt payment is actually made of.

A mortgage bill is rarely just the loan. It is principal and interest plus
whatever the servicer collects alongside it — property tax, homeowner's
insurance, mortgage insurance, an HOA fee — and only the P&I half has
anything to do with the debt. Every payoff figure in this app is computed
from principal and interest, so the payment on file has to be the P&I one,
and the rest of the bill had nowhere to be recorded at all.

That silence cost accuracy twice over. Somebody who entered their whole bill
as the "minimum payment" got a payoff date years early — caught, at least,
by `implied_never_pays_off` when the figure could not have amortized the
original loan. Somebody who entered P&I correctly then had no way to say what
the other several hundred a month was, so the app could not tell them their
transfers exceeded their stated payment, could not show them the bill they
actually pay, and could not notice that the mortgage insurance on the
composition should have come off once they passed twenty percent equity.

Components are OPTIONAL and additive. A car loan has none. Nothing here ever
changes a projection: P&I drives the schedule exactly as it did before, and
these are the parts sitting beside it.

Pure — no session, no model — so every rule below is a one-line test.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from igab.domain.money import quantize_cents

ZERO = Decimal("0")

#: What a component IS, as opposed to what it is called. The kind is the part
#: the app reasons about — `pmi` is the one with a rule attached — while the
#: label is the user's own wording ("County tax", "Flood").
ComponentKind = Literal["tax", "insurance", "pmi", "hoa", "other"]

COMPONENT_KINDS: tuple[ComponentKind, ...] = ("tax", "insurance", "pmi", "hoa", "other")

#: Offered as the default wording for each kind. The user may overwrite it.
DEFAULT_LABELS: dict[str, str] = {
    "tax": "Property tax",
    "insurance": "Homeowner's insurance",
    "pmi": "Mortgage insurance (PMI)",
    "hoa": "HOA dues",
    "other": "Other",
}

#: Lenders must drop borrower-requested PMI at 80% loan-to-value and cancel it
#: automatically at 78%. The app uses the request threshold, because telling
#: somebody the day they may ASK is the useful day.
PMI_EQUITY_THRESHOLD = Decimal("0.20")

MAX_COMPONENTS = 8
MAX_LABEL = 40


@dataclass(frozen=True)
class PaymentComponent:
    kind: ComponentKind
    label: str
    amount: Decimal

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "label": self.label, "amount": str(self.amount)}


class CompositionError(ValueError):
    """A component list that cannot be stored as given."""


def _amount(raw: Any, index: int) -> Decimal:
    try:
        value = quantize_cents(Decimal(str(raw)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CompositionError(f"Component {index + 1} has an amount that is not a number") from exc
    if value < ZERO:
        raise CompositionError(f"Component {index + 1} cannot be negative")
    return value


def parse_components(raw: Any) -> list[PaymentComponent]:
    """Validate a component list as it arrived over HTTP or out of the column.

    Refuses rather than repairs. A composition is a figure the user reads back
    off their mortgage statement to check the app agrees with it, so silently
    dropping a malformed row would produce a total that matches nothing.

    None and an empty list both mean "no composition on file", which is the
    ordinary case for every debt that is not a mortgage.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise CompositionError("Payment components must be a list")
    if len(raw) > MAX_COMPONENTS:
        raise CompositionError(f"At most {MAX_COMPONENTS} components")
    out: list[PaymentComponent] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CompositionError(f"Component {index + 1} is not an object")
        kind = item.get("kind", "other")
        if kind not in COMPONENT_KINDS:
            raise CompositionError(f"Component {index + 1} has an unknown kind {kind!r}")
        label = str(item.get("label") or DEFAULT_LABELS[kind]).strip()[:MAX_LABEL]
        if not label:
            label = DEFAULT_LABELS[kind]
        out.append(
            PaymentComponent(kind=kind, label=label, amount=_amount(item.get("amount"), index))
        )
    return out


def components_total(components: list[PaymentComponent]) -> Decimal:
    return quantize_cents(sum((c.amount for c in components), ZERO))


def full_monthly_payment(
    principal_and_interest: Decimal | None, components: list[PaymentComponent]
) -> Decimal | None:
    """The whole bill: P&I plus everything collected beside it.

    None when there is no P&I on file — a total built on a missing half would
    be a smaller number presented as a complete one, which is the failure this
    module exists to stop.
    """
    if principal_and_interest is None:
        return None
    return quantize_cents(principal_and_interest + components_total(components))


#: How far the observed pace may sit from the stated bill before it is worth
#: saying anything. Escrow moves annually and people round their transfers;
#: a note that fires on a rounding difference is a note people learn to skip.
MATCH_TOLERANCE = Decimal("0.02")


@dataclass(frozen=True)
class CompositionCheck:
    """Whether what the ledger sees agrees with what the user declared."""

    #: 'matches_full'    — transfers ≈ the whole declared bill
    #: 'matches_pi'      — transfers ≈ P&I, so escrow is paid elsewhere
    #: 'undeclared_gap'  — transfers exceed P&I and nothing explains the rest
    #: 'unknown'         — not enough on file to say
    verdict: Literal["matches_full", "matches_pi", "undeclared_gap", "unknown"]
    #: What the transfers exceed P&I by, when that is the finding.
    gap: Decimal | None = None


def check_composition(
    principal_and_interest: Decimal | None,
    components: list[PaymentComponent],
    typical_payment: Decimal | None,
) -> CompositionCheck:
    """Compare the declared payment with the one actually observed.

    The point is not to catch the user out; it is that the two readings mean
    different things and the app cannot tell which one it is looking at. A
    transfer of the whole bill into the mortgage account moves the balance by
    the escrow as well as the principal, so the debt appears to shrink faster
    than it does and every projection built on that balance runs early.

    `matches_pi` is the healthy shape: only P&I reaches the loan, escrow goes
    wherever escrow goes, and the ledger means what the schedule assumes.
    `matches_full` is honest but drifting, and worth saying so.
    `undeclared_gap` is the one nobody can act on without being told what the
    field is for — which is why the caller pairs the number with the advice.
    """
    if principal_and_interest is None or typical_payment is None:
        return CompositionCheck("unknown")
    if abs(typical_payment - principal_and_interest) <= MATCH_TOLERANCE:
        return CompositionCheck("matches_pi")
    gap = quantize_cents(typical_payment - principal_and_interest)
    if gap < ZERO:
        # Paying under P&I is a real situation with its own warnings
        # elsewhere (the payoff pill says the payments will not clear it).
        # It is not a composition problem.
        return CompositionCheck("unknown")
    total = components_total(components)
    if components and abs(gap - total) <= MATCH_TOLERANCE:
        return CompositionCheck("matches_full", gap=gap)
    return CompositionCheck("undeclared_gap", gap=gap)
