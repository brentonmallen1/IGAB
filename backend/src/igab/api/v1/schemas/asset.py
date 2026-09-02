import datetime
import uuid
from decimal import Decimal

from pydantic import Field

from igab.api.v1.schemas.base import ApiModel, ClientDated


class AssetOut(ApiModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    name: str
    #: 'property' | 'vehicle' | 'other' — nullable, like Liability.liability_type.
    asset_type: str | None
    #: The newest value point, as a pair that travels together — None until
    #: the first point is recorded, and an asset with no point contributes
    #: nothing to net worth. The date is part of the figure: a self-reported
    #: number that moves net worth UP carries its provenance everywhere.
    current_value: Decimal | None
    value_as_of: datetime.date | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class AssetCreate(ClientDated):
    name: str = Field(min_length=1, max_length=100)
    asset_type: str | None = None
    #: Optional first value point, recorded through the same newest-wins path
    #: as any later one.
    value: Decimal | None = Field(default=None, ge=0)
    value_as_of: datetime.date | None = None


class AssetUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    asset_type: str | None = None


class AssetValueOut(ApiModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    date: datetime.date
    value: Decimal
    source: str

    model_config = {"from_attributes": True}


class AssetValueCreate(ClientDated):
    value: Decimal = Field(ge=0)
    #: Defaults to the caller's today (`client_today`), and only then to the
    #: server's — see `clock.recorded_on`.
    date: datetime.date | None = None


class AssetValueUpdate(ApiModel):
    #: The date is a point's identity (one per day) — moving a point is a
    #: delete plus a new entry, never an edit.
    value: Decimal = Field(ge=0)
