"""Which categories a report is about, from the three ways a person can say it.

A report's scope can arrive as an explicit list of categories, as a saved
filter, or as a bare tag. All three mean the same kind of thing — a set of
category ids — and every report that accepts one should accept all three.

This exists before it is needed six times. The arithmetic was written once,
inline in `spending_trends_report`, alongside private `useState` controls in
`SpendingTrendsReport` that no other chart could see; extending it report by
report is exactly how this repo grew five copies of an anchored dropdown. So
the rule lives here, the endpoints take it as a dependency, and a report added
without it fails a test rather than quietly ignoring the scope the user set.

**Union, not intersection.** Each source ADDS to the scope: "these categories,
plus whatever carries this tag, plus whatever this filter names". That is what
the original inline version did, and it is the reading a person expects from
three controls sitting side by side — narrowing twice by accident is a much
worse surprise than widening.

**`None` is not an empty set.** None means "no scope was asked for", and every
report treats it as "everything". An empty set means "a scope was asked for and
nothing matched" — a tag nobody has applied yet — and must return nothing. A
resolver that collapsed the two would answer a question about an unused tag
with the entire budget.
"""

import uuid
from dataclasses import dataclass

from igab.repositories.budget_filter_repo import BudgetFilterRepository
from igab.repositories.tag_repo import TagRepository


@dataclass(frozen=True)
class CategoryScope:
    """The resolved scope, plus what could not be resolved.

    `category_ids` is None for "no scope asked for". `filter_unavailable` says
    a saved filter was named and could not be found — deleted in another tab,
    or belonging to another budget. That is reported rather than ignored: a
    stale id resolving to nothing would silently WIDEN the report to the whole
    budget, which looks like data appearing rather than a filter going missing.
    """

    category_ids: list[uuid.UUID] | None
    filter_unavailable: bool = False

    @property
    def is_scoped(self) -> bool:
        return self.category_ids is not None


async def resolve_category_scope(
    budget_id: uuid.UUID,
    *,
    category_ids: list[uuid.UUID] | None,
    filter_id: uuid.UUID | None,
    tag_ids: list[uuid.UUID] | None,
    filter_repo: BudgetFilterRepository,
    tag_repo: TagRepository,
) -> CategoryScope:
    """Fold the three sources into one set of category ids.

    A saved filter resolves through `BudgetFilterRepository.effective_category_ids`
    — its named categories plus everything carrying its tags — which is the same
    resolution the budget page reads, "so the two cannot disagree about which
    rows a filter means". Nothing here restates it.
    """
    asked = category_ids is not None or filter_id is not None or bool(tag_ids)
    if not asked:
        return CategoryScope(category_ids=None)

    scope: set[uuid.UUID] = set(category_ids or [])
    filter_unavailable = False

    if filter_id is not None:
        saved = await filter_repo.get_with_categories(filter_id)
        if saved is None or saved.budget_id != budget_id:
            filter_unavailable = True
        else:
            scope |= set((await filter_repo.effective_category_ids([saved]))[saved.id])

    if tag_ids:
        # Scoped to the budget by the repository, so a tag id from elsewhere
        # contributes nothing rather than reaching across budgets.
        scope |= await tag_repo.get_category_ids_by_tags(budget_id, tag_ids)

    # Sorted so the same request produces the same query text, which keeps
    # query plans and any downstream caching stable.
    return CategoryScope(
        category_ids=sorted(scope, key=str),
        filter_unavailable=filter_unavailable,
    )
