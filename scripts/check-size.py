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

**What counts is code lines, not raw lines.** Blank lines, comments, and
docstrings are free. Two reasons. First, this repository's culture is long
teaching docstrings, and a gate that taxes them is a gate arguing with
CLAUDE.md. Second, raw counts fail on noise: a formatter version reflowing
comments, or a rename pushing one line past 100 chars so it wraps, changed
nothing and still moved the number. Python is counted through `tokenize` + a
docstring pass over the AST; TypeScript through a small scanner (a line counts
when any token sits on it outside a comment; string contents are code). Known
blind spot: a `/*` inside a regex literal can fool the TS scanner into
swallowing lines — rare enough to accept in a gate, and it undercounts, which
errs toward passing. A file the Python tokenizer cannot parse falls back to
its raw line count rather than crashing the gate.

**This is a ratchet, not a freeze.** Files already over budget are recorded
below with the size they were at when the gate went in. They may shrink; they
may not grow past their lock plus a little slack. Everything else must come in
under budget. So:

- a new file over budget                    -> fails
- an over-budget file more than SLACK over  -> fails
- an over-budget file inside the slack      -> passes, noted
- an over-budget file getting better        -> passes, and says you can lower
                                               the number

The slack exists because a zero-growth ratchet fails on a stray import, and
what that buys is not smaller files — it is line-golf: collapsing a list or
re-routing an import to appease a counter, which makes the code worse in the
metric's name. Ten lines is under any real method; accretion still trips the
gate, noise no longer does. The ceiling itself NEVER rises — total drift is
bounded at lock + SLACK forever — and `--update` refuses to raise a number,
so re-locking wins can never quietly bake drift in.

Shrinking deliberately does NOT fail. Deleting two lines from a 3,600-line
service should not turn CI red on a bookkeeping detail — that is the kind of
friction that gets a gate deleted. The cost is that a ceiling can go stale, so
a file may drift back up to its lock (plus slack), but no further. `--update`
re-locks every ceiling at once when you want the win.

Usage:
    python3 scripts/check-size.py            # check (self-tests the counters first)
    python3 scripts/check-size.py --update   # rewrite OVER_BUDGET from the tree
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Code lines per file, by extension. Generous on purpose — this catches the
#: outliers that stop being readable, not ordinary long files.
BUDGET = {".py": 1000, ".ts": 600, ".tsx": 600}

#: How far past its lock an over-budget file may drift before the gate fails.
#: See the module docstring: this absorbs noise (an import, a reflow), not
#: methods. Flat, not a percentage — a percentage would hand the most slack to
#: the worst offenders.
SLACK = 10

#: Directories to walk. Tests are deliberately OUT: a table-driven suite is
#: long because it enumerates cases, which is the good kind of long.
ROOTS = ("backend/src", "frontend/src")

SKIP_SUFFIXES = (".test.ts", ".test.tsx", ".d.ts")

#: Files over budget when this gate went in, with the CODE-line count they
#: were locked at. Sorted by how far over they are — the top of this list is
#: the work. Lower a number when the file shrinks; delete the line when it
#: comes under budget. Never raise one (`--update` won't).
OVER_BUDGET: dict[str, int] = {
    "backend/src/igab/services/report_service.py": 2733,
    "frontend/src/components/transactions/TransactionEditor/TransactionEditor.tsx": 1159,
    "backend/src/igab/db/models.py": 1121,
    "backend/src/igab/repositories/transaction_repo.py": 1083,
    "backend/src/igab/api/v1/categories.py": 1028,
    "frontend/src/components/transactions/TransactionTable/TransactionTable.tsx": 926,
    "frontend/src/components/transactions/QuickAddSheet/QuickAddSheet.tsx": 847,
    "frontend/src/pages/SettingsPage/SettingsPage.tsx": 842,
    "frontend/src/pages/PayeesPage/PayeesPage.tsx": 794,
    "frontend/src/pages/BudgetSelectorPage/BudgetSelectorPage.tsx": 767,
    "frontend/src/types/index.ts": 745,
    "frontend/src/utils/searchParser.ts": 740,
    "frontend/src/components/budget/CreditCardsSection/CreditCardsSection.tsx": 735,
    "frontend/src/components/guide/tools/CategoryPlanner.tsx": 733,
    "frontend/src/components/transactions/TransactionRow/TransactionRow.tsx": 690,
    "frontend/src/pages/LiabilityPage/LiabilityPage.tsx": 650,
    "frontend/src/components/imports/ImportReviewDialog/ImportReviewDialog.tsx": 632,
}

_PY_NON_CODE_TOKENS = frozenset(
    {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
     tokenize.ENDMARKER}
)


def python_code_lines(text: str) -> int:
    """Lines carrying at least one code token: no blanks, comments, docstrings.

    A multi-line string that is NOT a docstring (a SQL constant, a template)
    counts in full — it is data the reader must hold, unlike prose about it.
    """
    try:
        tree = ast.parse(text)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, tokenize.TokenError, ValueError):
        # A file this tool cannot parse still gets a number — raw is honest
        # enough for a gate, and the real syntax error fails elsewhere first.
        return len(text.splitlines())

    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
            and body[0].end_lineno is not None
        ):
            doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))

    code_lines: set[int] = set()
    for tok in tokens:
        if tok.type in _PY_NON_CODE_TOKENS:
            continue
        code_lines.update(range(tok.start[0], tok.end[0] + 1))
    return len(code_lines - doc_lines)


def ts_code_lines(text: str) -> int:
    """Lines carrying anything outside a comment: no blanks, no comment-only
    lines. String and template-literal contents count — they are values.

    A character scanner, not a parser: it tracks strings ('/"/`), line
    comments, and block comments, with backslash escapes. It does not know
    regex literals, so `/*` inside one starts a phantom block comment — see
    the module docstring for why that is accepted.
    """
    count = 0
    in_block = False
    in_string: str | None = None
    for line in text.splitlines():
        has_code = False
        i, n = 0, len(line)
        while i < n:
            ch = line[i]
            if in_string:
                has_code = True
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_string:
                    in_string = None
                i += 1
                continue
            if in_block:
                if ch == "*" and i + 1 < n and line[i + 1] == "/":
                    in_block = False
                    i += 2
                    continue
                i += 1
                continue
            if ch in " \t":
                i += 1
                continue
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                break
            if ch == "/" and i + 1 < n and line[i + 1] == "*":
                in_block = True
                i += 2
                continue
            if ch in "'\"`":
                in_string = ch
                has_code = True
                i += 1
                continue
            has_code = True
            i += 1
        if in_string and in_string != "`":
            in_string = None  # ' and " cannot span lines; ` legitimately does
        if has_code:
            count += 1
    return count


def code_lines(path: Path, text: str) -> int:
    return python_code_lines(text) if path.suffix == ".py" else ts_code_lines(text)


def _self_test() -> None:
    """The counters' contract, enforced on every run — a gate whose meter
    drifts fails silently everywhere, so the meter checks itself first."""
    py = '"""Module doc.\n\nTwo lines of prose.\n"""\n\n# comment\nx = 1\n\ny = (\n    2\n)\n'
    assert python_code_lines(py) == 4, python_code_lines(py)  # x=1, y=(, 2, )
    py_sql = 'q = """\nSELECT 1\n"""\n'
    assert python_code_lines(py_sql) == 3, python_code_lines(py_sql)  # not a docstring
    py_fn = 'def f():\n    """Doc."""\n    return 1\n'
    assert python_code_lines(py_fn) == 2, python_code_lines(py_fn)
    ts = "// header\n\nconst a = 1; // trailing\n/*\n block\n*/\nconst b = `x\n\ny`;\n"
    # a-line and the template's two non-blank lines; the blank inside is free
    assert ts_code_lines(ts) == 3, ts_code_lines(ts)
    ts_mixed = "const c = 1; /* open\nstill comment */ const d = 2;\n"
    assert ts_code_lines(ts_mixed) == 2, ts_code_lines(ts_mixed)
    ts_str = 'const u = "http://x"; // real comment\n'
    assert ts_code_lines(ts_str) == 1, ts_code_lines(ts_str)


def measure() -> dict[str, int]:
    """Every in-scope file and its code-line count, repo-relative."""
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
            found[rel] = code_lines(path, path.read_text(encoding="utf-8"))
    return found


def main() -> int:
    _self_test()
    sizes = measure()

    if "--update" in sys.argv:
        over = {
            rel: n for rel, n in sorted(sizes.items(), key=lambda kv: -kv[1])
            if n > BUDGET[Path(rel).suffix]
        }
        for rel, n in over.items():
            # min(): re-locking is for banking wins, never for blessing drift.
            print(f'    "{rel}": {min(n, OVER_BUDGET.get(rel, n))},')
        print(f"\n{len(over)} files over budget — paste the block above into OVER_BUDGET.")
        return 0

    problems: list[str] = []
    notes: list[str] = []

    for rel, allowed in sorted(OVER_BUDGET.items()):
        actual = sizes.get(rel)
        if actual is None:
            problems.append(
                f"{rel}: listed in OVER_BUDGET but not found — delete the line "
                f"(the file moved or went away)."
            )
        elif actual > allowed + SLACK:
            problems.append(
                f"{rel}: {actual} code lines, up from its lock of {allowed} (slack is "
                f"{SLACK}). This file is already over the {BUDGET[Path(rel).suffix]}-line "
                f"budget; it may shrink, not grow. Put the new code somewhere a reader "
                f"can find it."
            )
        elif actual > allowed:
            notes.append(
                f"{rel}: {actual} code lines, {actual - allowed} over its lock of "
                f"{allowed} — inside the slack, but the direction is wrong."
            )
        elif actual < allowed:
            # Not a problem — a win. Noted, never fatal: see the module
            # docstring on why shrinking must not turn the build red.
            notes.append(
                f"{rel}: {actual} code lines, down from {allowed}"
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
                f"{rel}: {actual} code lines, over the {budget}-line budget. Split it, or "
                f"— if it genuinely has to be this long — add it to OVER_BUDGET in "
                f"scripts/check-size.py with a reason in the commit message."
            )

    for note in notes:
        print(f"  · {note}")

    if problems:
        print("\nFile-length budget:\n" if notes else "File-length budget:\n")
        for p in problems:
            print(f"  ✗ {p}")
        print(f"\n{len(problems)} problem(s). `--update` reprints the OVER_BUDGET block.")
        return 1

    print(f"File-length budget: {len(sizes)} files, {len(OVER_BUDGET)} on the debt list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
