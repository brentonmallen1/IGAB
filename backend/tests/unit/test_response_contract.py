"""Required response fields must exist in the hand-written TypeScript types.

There is no codegen at this seam: `frontend/src/types/index.ts` is written by
hand and `apiClient.get<Transaction[]>` is an unchecked assertion, so nothing
fails when the two drift.

Only one direction is silent, and it is the one this checks. An *extra* TS
field is already a compile error, and an extra Pydantic field is harmless. A
**required** response field the TS interface does not declare is the dangerous
case: the client reads `undefined` and treats it as `false`, which is exactly
the shape `needs_category` had — a row reporting unfiled work as filed.

**This is a backstop for forgetfulness, not the guarantee.** No name-matching
check catches TS declaring `needs_category: boolean` while the server sends
null. Only the convention of making a served field REQUIRED in Pydantic
catches that, and it catches it server-side at serialization, before the
client ever sees it. Keep doing that; this test only notices when someone adds
a field and forgets the other file.
"""

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from igab.api.v1.schemas.account import AccountResponse
from igab.api.v1.schemas.category import (
    BudgetMonthResponse,
    CategoryBalance,
    CategoryResponse,
)
from igab.api.v1.schemas.transaction import TransactionResponse

TS_TYPES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "types" / "index.ts"

#: Pydantic model → TypeScript interface name.
#:
#: An allowlist, not every response model. Mapping all ~120 is where both the
#: cost and the false positives live — renames, inline types, models the client
#: never fetches, and the 18KB of Report* payloads. These are the ones carrying
#: served rules, which is what makes a drift here expensive. One line to extend.
CONTRACT: dict[type[BaseModel], str] = {
    TransactionResponse: "Transaction",
    CategoryResponse: "Category",
    CategoryBalance: "CategoryBalance",
    BudgetMonthResponse: "BudgetMonth",
    AccountResponse: "Account",
}


def _ts_interface_fields(name: str) -> set[str]:
    """Field names declared on `export interface <name>`.

    Regex rather than a TS parser: a TypeScript AST dependency in the *backend*
    test environment costs more than fifteen lines of regex. If the interface
    cannot be found this raises — it must never skip, or a reformat would make
    the check quietly pass forever.
    """
    source = TS_TYPES.read_text()
    match = re.search(
        rf"^export interface {re.escape(name)} \{{(.*?)^\}}", source, re.S | re.M
    )
    if match is None:
        raise AssertionError(
            f"No `export interface {name}` in {TS_TYPES}. If it was renamed, update CONTRACT."
        )
    body = match.group(1)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)  # strip JSDoc
    body = re.sub(r"//[^\n]*", "", body)
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", body, re.M))


@pytest.mark.parametrize(
    ("model", "ts_name"), list(CONTRACT.items()), ids=[m.__name__ for m in CONTRACT]
)
def test_required_fields_exist_in_typescript(model: type[BaseModel], ts_name: str):
    declared = _ts_interface_fields(ts_name)
    required = {
        name for name, field in model.model_fields.items() if field.is_required()
    }
    missing = sorted(required - declared)
    assert not missing, (
        f"{model.__name__} requires {missing}, which `interface {ts_name}` does not declare. "
        f"The client will read undefined and treat it as false. Add the field to "
        f"{TS_TYPES.relative_to(TS_TYPES.parents[3])}."
    )


def test_the_types_file_is_where_we_think_it_is():
    # Guards the whole suite: a moved file would make every check above pass by
    # never finding anything to disagree with.
    assert TS_TYPES.is_file(), TS_TYPES
