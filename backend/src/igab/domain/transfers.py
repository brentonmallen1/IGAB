"""Where a category may sit on a transaction.

The rule, stated once:

    A category may sit only on an ON-BUDGET row — and on a transfer leg,
    only when the partner is OFF-budget.

The first clause is the general rule: a category files budget spending, and a
tracking account's rows are net-worth movement, not budget spending. A
categorized row on an off-budget account moved envelopes (and, via the
carryover floor, Ready to Assign) while its account contributed to no balance
term — money moving with no on-budget event.

The second clause is the transfer case: a category on a transfer means a YNAB
"spending transfer", real spending or income crossing the budget boundary. An
on↔on transfer is internal movement and can never be categorized (it would
count moving money as spending); an off-budget leg can never be categorized;
both legs categorized is always wrong.

This rule was found hand-written three times — transfer create, the
transfer-edit planner, and the YNAB importer's pairing check — each phrased
for its own call shape, and the fourth path that needed it (`repair_transfers`)
had none, so the auto-repair happily created exactly the categorized
on↔on link the manual paths refuse. One implementation, per CLAUDE.md.

Pure: takes booleans, returns the verdict. Messages stay at the call sites,
where they can speak in that path's terms; the *decision* is only here.
"""


def leg_may_carry_category(own_on_budget: bool, partner_on_budget: bool | None = None) -> bool:
    """May THIS row hold a category? A plain transaction is a leg with no
    partner — the general clause alone decides it."""
    if partner_on_budget is None:
        return own_on_budget
    return own_on_budget and not partner_on_budget


def pair_may_carry_category(a_on_budget: bool, b_on_budget: bool) -> bool:
    """May a category exist anywhere on this pair? True iff exactly one side
    is on-budget — the category then belongs to that side
    (`leg_may_carry_category` says which)."""
    return leg_may_carry_category(a_on_budget, b_on_budget) or leg_may_carry_category(
        b_on_budget, a_on_budget
    )


def linking_breaks_category_rule(
    a_categorized: bool,
    a_on_budget: bool,
    b_categorized: bool,
    b_on_budget: bool,
) -> bool:
    """Would linking these two concrete legs as one transfer put a category
    somewhere the rule forbids? Used by the paths that join *existing* rows
    (import pairing, the repair pass) rather than creating fresh ones."""
    if a_categorized and b_categorized:
        return True
    if a_categorized:
        return not leg_may_carry_category(a_on_budget, b_on_budget)
    if b_categorized:
        return not leg_may_carry_category(b_on_budget, a_on_budget)
    return False
