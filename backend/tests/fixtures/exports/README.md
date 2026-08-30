# Frozen export and snapshot fixtures

Each directory here is one budget, written by the code as it stood on that
date, in that format version. `test_import_compatibility.py` reads every one
of them: proof that a file written then still imports now, and still means the
same numbers.

```
exports/v1-2026-08/sample-full.igab-export.zip     the YNAB-shaped export
snapshots/v1-2026-08/sample-full.igab.zip          the lossless snapshot
exports/expected/v1-2026-08.json                   what those files MEANT
```

## Never regenerate an existing fixture. Add a new one.

`capture_budget_fixtures.py` refuses to write into a directory that already
exists, because this is the rule that decides whether the suite is worth
anything. Regenerating is how a backwards-compatibility suite goes green
forever while testing nothing — and it will always look like the right fix
when a test goes red, because the diff looks like noise.

It is not noise. A red test here means the format changed. Either that change
is deliberate, in which case **add a directory**, or it is a bug, in which case
the fixture just caught one.

```
python scripts/capture_budget_fixtures.py --new
```

Add one whenever `format_version`, a member name, or a column set changes.
Those are the only three things that can break a reader.

## `expected/<version>.json` is a contract

It records what the budget in that file produced — Ready to Assign, total
overspent, and every category's assigned / activity / available, month by
month, to the cent. It is **never** edited to match new behaviour. If a
genuine bug fix changes what an old file should produce, that is a deliberate
diff with a reason in the commit message, and it is exactly the diff a
reviewer needs to see.

## Dropping support is a visible act

`MIN_SUPPORTED_VERSION` and `MIN_SUPPORTED_REVISION` in
`domain/snapshot_format.py` are the only places compatibility may be dropped,
and raising either must delete the fixtures it orphans **in the same commit**.
"We no longer read v1" should be a reviewed decision, not a test quietly
starting to skip.

## The data is generated, never captured

Every fixture comes from `SampleBudgetGenerator` at the full tier, at a fixed
anchor date, so it holds splits, transfers, off-budget accounts, a credit
card, hidden categories, targets, tags, scheduled transactions and liabilities
— and no real person is anywhere near it. This repository is public
(CLAUDE.md). `check-pii.py` reads inside these zips, which it could not do
before this corpus existed.
