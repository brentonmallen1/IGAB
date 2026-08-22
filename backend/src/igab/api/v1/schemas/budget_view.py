import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BudgetViewGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int


class BudgetViewPlacementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: uuid.UUID
    #: None means placed in the view but in no group — rendered under
    #: "Unassigned", the same bucket categories with no placement fall into.
    group_id: uuid.UUID | None
    sort_order: int
    is_hidden: bool


class BudgetViewPlacementInput(BaseModel):
    category_id: uuid.UUID
    group_id: uuid.UUID | None = None
    sort_order: int = 0
    is_hidden: bool = False


class BudgetViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    #: Group names in display order. Ids are assigned server-side; placements
    #: are sent in a follow-up PATCH once the client knows them.
    groups: list[str] = Field(default_factory=list)


class BudgetViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = None
    groups: list[str] | None = None
    placements: list[BudgetViewPlacementInput] | None = None


class BudgetViewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    sort_order: int
    groups: list[BudgetViewGroupResponse]
    placements: list[BudgetViewPlacementResponse]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _sort_placements(self) -> "BudgetViewResponse":
        # Stable order so the client can render without re-sorting, and so a
        # response diff is meaningful in tests.
        self.placements.sort(key=lambda p: (p.sort_order, str(p.category_id)))
        return self
