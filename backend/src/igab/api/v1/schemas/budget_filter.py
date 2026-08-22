import datetime
import uuid

from pydantic import BaseModel, model_validator

from igab.db.models import BudgetFilter


class BudgetFilterCreate(BaseModel):
    name: str
    category_ids: list[uuid.UUID] = []


class BudgetFilterUpdate(BaseModel):
    name: str | None = None
    category_ids: list[uuid.UUID] | None = None


class BudgetFilterResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    sort_order: int
    category_ids: list[uuid.UUID]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_category_ids(cls, data: object) -> object:
        if isinstance(data, BudgetFilter):
            return {
                "id": data.id,
                "budget_id": data.budget_id,
                "name": data.name,
                "sort_order": data.sort_order,
                "category_ids": [sel.category_id for sel in data.category_selections],
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data
