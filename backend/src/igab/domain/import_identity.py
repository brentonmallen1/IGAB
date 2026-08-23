"""One definition of a transaction's import identity.

`Transaction.import_id` is what makes importing the same file twice a no-op.
It is persisted and enforced by a unique index on `(account_id, import_id)`,
so the rule that derives it is a data contract, not an implementation detail.

There used to be two `_generate_import_id` functions with the same name, the
same `csv:` prefix and the same hash construction, differing only in their key
material: the CSV importer keyed on the account's **UUID**, the YNAB importer
on the account's **name**. Both wrote the same column and were checked by the
same query. The reachable consequence: rows imported from a CSV into a budget
created by a YNAB import never deduplicated against each other, because the
two paths derived different ids for identical transactions.

The amount is quantized before hashing. `Decimal("10.00")` and
`Decimal("10.0000")` are the same money and hash differently otherwise, and
`Numeric(19,4)` normalizes scale on the round trip anyway — so an id computed
before insert would not match one recomputed after.
"""

import hashlib
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

_CENTS = Decimal("0.01")


def generate_import_id(account_id: uuid.UUID, txn_date: date, amount: Decimal, payee: str) -> str:
    """Stable identity for an imported row: same transaction, same id.

    Keyed on `account_id` rather than the account's name so renaming an
    account does not change the identity of transactions that have not moved.
    """
    content = f"{account_id}|{txn_date.isoformat()}|{amount.quantize(_CENTS)}|{payee}"
    return f"csv:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


def disambiguate_in_batch(rows: Sequence[Any]) -> None:
    """Make import_ids unique within one batch, in place.

    Two genuinely distinct transactions can share (account, date, amount,
    payee) — a real double charge — and hash identically. Suffixing ":N" lets
    both import while the unique index holds.

    Order-stable, which is the property that matters: re-importing the same
    file assigns the same suffixes, so the second run still deduplicates
    instead of inserting a parallel set of rows.

    Keying on `import_id` alone is sufficient now that the id is derived from
    `account_id` — the account is already inside the hash.

    Typed loosely because the two callers build different row shapes: the CSV
    importer a TypedDict, the YNAB importer a plain dict. Both are mutable
    mappings carrying "import_id", which is all this touches.
    """
    seen: dict[str, int] = {}
    for row in rows:
        base = row.get("import_id")
        if not base:
            continue
        count = seen.get(base, 0)
        if count > 0:
            row["import_id"] = f"{base}:{count}"
        seen[base] = count + 1
