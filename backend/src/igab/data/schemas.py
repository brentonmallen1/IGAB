"""Polars schema definitions mirroring SQLAlchemy models."""
import polars as pl
from polars.type_aliases import PolarsDataType

TRANSACTION_SCHEMA: dict[str, PolarsDataType] = {
    "id": pl.String,
    "budget_id": pl.String,
    "account_id": pl.String,
    "date": pl.Date,
    "amount": pl.Decimal(precision=19, scale=4),
    "payee_id": pl.String,
    "category_id": pl.String,
    "memo": pl.String,
    "cleared": pl.String,
    "approved": pl.Boolean,
    "transfer_id": pl.String,
    "parent_transaction_id": pl.String,
    "is_split": pl.Boolean,
    "import_id": pl.String,
    "import_batch_id": pl.String,
}

ACCOUNT_SCHEMA: dict[str, PolarsDataType] = {
    "id": pl.String,
    "budget_id": pl.String,
    "name": pl.String,
    "account_type": pl.String,
    "on_budget": pl.Boolean,
    "is_closed": pl.Boolean,
    "sort_order": pl.Int32,
    "note": pl.String,
}

PAYEE_SCHEMA: dict[str, PolarsDataType] = {
    "id": pl.String,
    "budget_id": pl.String,
    "name": pl.String,
    "default_category_id": pl.String,
}

CATEGORY_SCHEMA: dict[str, PolarsDataType] = {
    "id": pl.String,
    "budget_id": pl.String,
    "category_group_id": pl.String,
    "name": pl.String,
    "sort_order": pl.Int32,
    "is_hidden": pl.Boolean,
}

BUDGET_ASSIGNMENT_SCHEMA: dict[str, PolarsDataType] = {
    "id": pl.String,
    "budget_id": pl.String,
    "category_id": pl.String,
    "month": pl.Date,
    "assigned": pl.Decimal(precision=19, scale=4),
}

# Columns needed for bulk CSV import insert (UUIDs generated in Python)
TRANSACTION_INSERT_COLUMNS = [
    "id",
    "budget_id",
    "account_id",
    "date",
    "amount",
    "payee_id",
    "category_id",
    "memo",
    "cleared",
    "approved",
    "import_id",
    "import_batch_id",
    "is_split",
    "is_deleted",
]
