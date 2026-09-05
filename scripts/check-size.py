#!/usr/bin/env python3
"""File-length budget, so a file stays something you can hold in your head.

**Why size and not just complexity.** Cyclomatic complexity says how tangled a
function is; length says whether anyone — or any tool loading context — can read
the file in one pass and be sure what is in it. A 3,600-line service is where
"grep the constant, count the copies" (CLAUDE.md's first rule) quietly stops
happening, because nobody reads to the end. The two metrics catch different
things and ruff already covers the other one (C901 / PLR0912 / PLR0915).

Ruff has no file-length rule, and eslint's `max-lines` would only cover half the
tree, so the budget for both halves lives here — one place, one debt list, one
number to watch.

**This is a ratchet, not a freeze.** Files already over budget are recorded
below with the size they were at when the gate went in. They may shrink; they
may not grow. Everything else must come in under budget. So:

- a new file over budget             -> fails
- an over-budget file getting worse  -> fails
- an over-budget file getting better -> passes, and says you can lower the number

The last one deliberately does NOT fail. Deleting two lines from a 3,600-line
service should not turn CI red on a bookkeeping detail — that is the kind of
friction that gets a gate deleted. The cost is that a ceiling can go stale, so
a file may drift back up to the number it was on the day this went in, but no
further. `--update` re-locks every ceiling at once when you want the win.

Usage:
    python3 scripts/check-size.py            # check
    python3 scripts/check-size.py --update   # rewrite OVER_BUDGET from the tree
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Lines per file, by extension. Generous on purpose — this catches the
#: outliers that stop being readable, not ordinary long files.
BUDGET = {".py": 1000, ".ts": 600, ".tsx": 600}

#: Directories to walk. Tests are deliberately OUT: a table-driven suite is
#: long because it enumerates cases, which is the good kind of long.
ROOTS = ("backend/src", "frontend/src")

SKIP_SUFFIXES = (".test.ts", ".test.tsx", ".d.ts")

#: Files over budget when this gate went in, with the size they were at.
#: Sorted by how far over they are — the top of this list is the work.
#: Lower a number when the file shrinks; delete the line when it comes under
#: budget. Never raise one.
OVER_BUDGET: dict[str, int] = {
    "backend/src/igab/services/report_service.py": 3607,
    "backend/src/igab/db/models.py": 1880,
    "backend/src/igab/repositories/transaction_repo.py": 1534,
    "backend/src/igab/services/budget_service.py": 1449,
    "backend/src/igab/services/category_service.py": 1407,
    "backend/src/igab/services/transaction_service.py": 1361,
    "frontend/src/components/transactions/TransactionEditor/TransactionEditor.tsx": 1313,
    "backend/src/igab/api/v1/categories.py": 1252,
    "backend/src/igab/sample_budget/card_scenarios.py": 1249,
    "frontend/src/types/index.ts": 1141,
    "frontend/src/components/transactions/TransactionTable/TransactionTable.tsx": 1060,
    "backend/src/igab/sample_budget/generator.py": 1045,
    "backend/src/igab/services/account_hygiene.py": 1045,
    "frontend/src/utils/searchParser.ts": 989,
    "frontend/src/components/transactions/QuickAddSheet/QuickAddSheet.tsx": 968,
    "frontend/src/pages/SettingsPage/SettingsPage.tsx": 927,
    "frontend/src/pages/PayeesPage/PayeesPage.tsx": 857,
    "frontend/src/components/budget/CreditCardsSection/CreditCardsSection.tsx": 839,
    "frontend/src/pages/BudgetSelectorPage/BudgetSelectorPage.tsx": 832,
    "frontend/src/components/guide/tools/CategoryPlanner.tsx": 812,
    "frontend/src/components/transactions/TransactionRow/TransactionRow.tsx": 783,
    "frontend/src/content/roadmap.ts": 712,
    "frontend/src/pages/LiabilityPage/LiabilityPage.tsx": 707,
    "frontend/src/components/imports/ImportReviewDialog/ImportReviewDialog.tsx": 702,
    "frontend/src/api/transactions.ts": 626,
}


def measure() -> dict[str, int]:
    """Every in-scope file and its line count, repo-relative."""
    found: dict[str, int] = {}
    for root in ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in BUDGET:
                continue
            name = path.name
            if any(name.endswith(s) for s in SKIP_SUFFIXES):
                continue
            rel = path.relative_to(ROOT).as_posix()
            found[rel] = len(path.read_text(encoding="utf-8").splitlines())
    return found


def main() -> int:
    sizes = measure()

    if "--update" in sys.argv:
        over = {
            rel: n for rel, n in sorted(sizes.items(), key=lambda kv: -kv[1])
            if n > BUDGET[Path(rel).suffix]
        }
        for rel, n in over.items():
            print(f'    "{rel}": {n},')
        print(f"\n{len(over)} files over budget — paste the block above into OVER_BUDGET.")
        return 0

    problems: list[str] = []
    wins: list[str] = []

    for rel, allowed in sorted(OVER_BUDGET.items()):
        actual = sizes.get(rel)
        if actual is None:
            problems.append(
                f"{rel}: listed in OVER_BUDGET but not found — delete the line "
                f"(the file moved or went away)."
            )
        elif actual > allowed:
            problems.append(
                f"{rel}: {actual} lines, up from {allowed}. This file is already over "
                f"the {BUDGET[Path(rel).suffix]}-line budget; it may shrink, not grow. "
                f"Put the new code somewhere a reader can find it."
            )
        elif actual < allowed:
            # Not a problem — a win. Noted, never fatal: see the module
            # docstring on why shrinking must not turn the build red.
            wins.append(
                f"{rel}: {actual} lines, down from {allowed}"
                + (
                    " — under budget now, delete its line."
                    if actual <= BUDGET[Path(rel).suffix]
                    else " — lower its number to lock that in."
                )
            )

    for rel, actual in sorted(sizes.items()):
        if rel in OVER_BUDGET:
            continue
        budget = BUDGET[Path(rel).suffix]
        if actual > budget:
            problems.append(
                f"{rel}: {actual} lines, over the {budget}-line budget. Split it, or "
                f"— if it genuinely has to be this long — add it to OVER_BUDGET in "
                f"scripts/check-size.py with a reason in the commit message."
            )

    for w in wins:
        print(f"  · {w}")

    if problems:
        print("\nFile-length budget:\n" if wins else "File-length budget:\n")
        for p in problems:
            print(f"  ✗ {p}")
        print(f"\n{len(problems)} problem(s). `--update` reprints the OVER_BUDGET block.")
        return 1

    print(f"File-length budget: {len(sizes)} files, {len(OVER_BUDGET)} on the debt list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
