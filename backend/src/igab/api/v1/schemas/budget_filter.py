import datetime
import uuid

from igab.api.v1.schemas.base import ApiModel
from igab.db.models import BudgetFilter


class BudgetFilterCreate(ApiModel):
    name: str
    category_ids: list[uuid.UUID] = []
    #: Any category carrying one of these tags is in the filter, now and as
    #: tags change. Optional and empty by default: a filter may be a plain
    #: list, a tag rule, or both.
    tag_ids: list[uuid.UUID] = []


class BudgetFilterUpdate(ApiModel):
    name: str | None = None
    category_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] | None = None


class BudgetFilterResponse(ApiModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    sort_order: int
    #: The categories named outright.
    category_ids: list[uuid.UUID]
    tag_ids: list[uuid.UUID]
    #: What the filter includes right now — the named categories plus every
    #: category carrying one of its tags. The grid reads THIS; it does not
    #: re-derive the union, because a report handed a filter_id resolves it
    #: on the server and the two must agree (BudgetFilterRepository
    #: .effective_category_ids).
    category_ids_effective: list[uuid.UUID]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    @classmethod
    def from_row(cls, row: BudgetFilter, effective: list[uuid.UUID]) -> "BudgetFilterResponse":
        return cls(
            id=row.id,
            budget_id=row.budget_id,
            name=row.name,
            sort_order=row.sort_order,
            category_ids=[sel.category_id for sel in row.category_selections],
            tag_ids=[sel.tag_id for sel in row.tag_selections],
            category_ids_effective=effective,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
