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

import inspect
import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from igab.api.v1.schemas.account import AccountResponse
from igab.api.v1.schemas.category import (
    BudgetMonthResponse,
    CardStatusOut,
    CategoryBalance,
    CategoryGroupResponse,
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
    CategoryGroupResponse: "CategoryGroup",
    CategoryBalance: "CategoryBalance",
    CardStatusOut: "CardStatus",
    BudgetMonthResponse: "BudgetMonth",
    AccountResponse: "Account",
}


#: Row bookkeeping, not served rules. A client interface may declare these or
#: not — several do — but requiring them buys nothing and costs something real:
#: the synthetic groups a saved view builds client-side have no timestamps to
#: give, so demanding them would push invented ones into the code the check
#: exists to protect. Fields that encode a *rule* are what this suite is for.
AUDIT_FIELDS = {"created_at", "updated_at"}


def _ts_interface_fields(name: str) -> set[str]:
    """Field names declared on `export interface <name>`.

    Regex rather than a TS parser: a TypeScript AST dependency in the *backend*
    test environment costs more than fifteen lines of regex. If the interface
    cannot be found this raises — it must never skip, or a reformat would make
    the check quietly pass forever.
    """
    source = TS_TYPES.read_text()
    match = re.search(rf"^export interface {re.escape(name)} \{{(.*?)^\}}", source, re.S | re.M)
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
    required = {name for name, field in model.model_fields.items() if field.is_required()}
    missing = sorted(required - declared - AUDIT_FIELDS)
    assert not missing, (
        f"{model.__name__} requires {missing}, which `interface {ts_name}` does not declare. "
        f"The client will read undefined and treat it as false. Add the field to "
        f"{TS_TYPES.relative_to(TS_TYPES.parents[3])}."
    )


def test_the_types_file_is_where_we_think_it_is():
    # Guards the whole suite: a moved file would make every check above pass by
    # never finding anything to disagree with.
    assert TS_TYPES.is_file(), TS_TYPES


def test_every_schema_inherits_the_api_base():
    """Money crosses the wire as a JSON number, and one `BaseModel` reintroduces
    a string for its whole model.

    That is not a loud failure. `tsc` cannot tell `"0.00"` from `0`, so the
    client keeps compiling and starts misbehaving quietly: `"0.00" !== 0` drew
    "$0.00" where the code said "—", `+` concatenated into NaN, and `>=`
    compared lexicographically. The workaround had reached 444 `Number(...)`
    wrappings before anyone noticed, which is what a missing mechanism looks
    like — invisible exactly where it was forgotten.
    """
    import importlib
    import pkgutil

    import igab.api.v1.schemas as pkg
    from igab.api.v1.schemas.base import ApiModel

    offenders = []
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        mod = importlib.import_module(f"{pkg.__name__}.{mod_info.name}")
        for name, obj in vars(mod).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModel)
                and obj.__module__ == mod.__name__
                and obj is not ApiModel
                and not issubclass(obj, ApiModel)
            ):
                offenders.append(f"{mod_info.name}.{name}")

    assert not offenders, (
        f"These schemas inherit BaseModel rather than ApiModel, so their Decimal "
        f"fields serialize as strings while the TypeScript calls them number: "
        f"{sorted(offenders)}. Inherit `ApiModel` from schemas/base.py."
    )


def _ts_field_types(name: str) -> dict[str, str]:
    """Field name → its declared TypeScript type, for one interface."""
    match = re.search(rf"export interface {name} \{{(.*?)\n\}}", TS_TYPES.read_text(), re.S)
    assert match, f"No `export interface {name}` in {TS_TYPES}."
    body = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S))
    return {
        m.group(1): m.group(2).strip().rstrip(",")
        for m in re.finditer(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:\s*([^\n]+)$", body, re.M)
    }


@pytest.mark.parametrize(
    ("model", "ts_name"), list(CONTRACT.items()), ids=[m.__name__ for m in CONTRACT]
)
def test_decimal_fields_are_numbers_in_typescript(model: type[BaseModel], ts_name: str):
    """A `Decimal` field must be `number` on the client, and now is one on the
    wire too (`schemas/base.py`).

    This is the half that was missing. The name check above passes whether the
    client says `number` or `string`, and the server was sending a string while
    every interface said `number` — a disagreement no compiler could see, which
    is how it survived long enough to grow 444 `Number(...)` wrappings and
    reach the screen as "$0.00" where the code said "—".
    """
    declared = _ts_field_types(ts_name)
    wrong = {
        field: declared[field]
        for field, info in model.model_fields.items()
        if field in declared
        and _mentions_decimal(info.annotation)
        and "number" not in declared[field]
    }
    assert not wrong, (
        f"{model.__name__} serializes these as JSON numbers, but `interface {ts_name}` "
        f"declares them otherwise: {wrong}. A string here compiles and then misbehaves "
        f'quietly — "0.00" !== 0, "9" >= "10", and + concatenates.'
    )


def _mentions_decimal(annotation: object) -> bool:
    from decimal import Decimal
    from typing import get_args

    if annotation is Decimal:
        return True
    return any(_mentions_decimal(a) for a in get_args(annotation))
