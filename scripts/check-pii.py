#!/usr/bin/env python3
"""Refuse to ship personal data. Runs in CI; run it before you commit.

This repository is public, and it has already leaked once: a captured
SimpleFIN response with 250 real transactions — two people's names, a mortgage
account number, a student loan number, a life insurance policy number, a
medical payment plan. It went in under a sanitizer whose docstring promised to
strip names and whose code had no name handling at all, and no test ever
loaded the file. Prose did not stop it. This is the mechanism that does.

Two checks:

1. **Literals that must never come back.** Everything the leak contained, by
   name. Add to `FORBIDDEN` whenever a real one is found and removed — the
   list is a ratchet, and it is the only part of this that knows what *your*
   real data looks like.

2. **Captured API responses.** The leak was one: a fixture saved straight from
   the bank's feed. Any JSON under a fixtures directory carrying transaction
   shape (`description` + `posted`, or a `payee` field) has to be declared in
   `REVIEWED_FIXTURES` — a line someone can only add after reading the file,
   which is the step that did not happen.

A digit-run heuristic was tried here and removed: it fired on UUIDs, on
`1234567890`, on dates, on `99999999999999`. A check that cries wolf a hundred
times is a check that gets deleted, and then there is no check.

Exit 1 on any finding, with the file and line, so CI fails loudly rather than
leaving it for someone to notice.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Real-world identifiers that reached this repo once and must not return.
#: Names, employers, and the institutions tied to specific accounts. Not
#: merchant chains — "Nordstrom" identifies nobody; "DOE, JANE" does.
FORBIDDEN = [
    "Doe", "DOE", "Jane", "JANE", "Alex", "ALEX",
    "Payserv", "PAYSERV",
    "Cedarbrook Loan", "CEDARBROOK", "Northshore", "NORTHSHORE",
    "Beacon Life", "BEACON LIFE", "Rivergas Utility", "RIVERGAS UTILITY",
    "Clinicpay", "CLINICPAY", "STATEREV", "DONATIONHUB",
]

#: Same, but only meaningful as whole words — too short or too common to match
#: as substrings (`NORTHWIND` is inside `adapter`; `Sapphire` is inside `Sapphirezen`).
FORBIDDEN_WORDS = ["NORTHWIND", "Sapphire", "SAPPHIRE"]

#: Fixture files that have been read end to end and are known to be fiction.
#: Adding a line here is the review; do not add one for a file you have not
#: opened.
REVIEWED_FIXTURES: set[str] = {
    "backend/tests/fixtures/ynab/Parity Budget - Plan.csv",
    "backend/tests/fixtures/ynab/Parity Budget - Register.csv",
}

#: A saved bank feed, by shape rather than by name.
FEED_SHAPE = (re.compile(r'"description"\s*:'), re.compile(r'"posted"\s*:'), re.compile(r'"payee"\s*:'))

#: Functional references to the repo's own public URLs. The owner's GitHub
#: handle is not a leak — it is the address of the project.
ALLOW_LINE = re.compile(r"brentonmallen1/IGAB|ghcr\.io/brentonmallen1|githubusercontent\.com")

SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2")


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [ROOT / p.decode() for p in out.split(b"\0") if p]


def main() -> int:
    findings: list[str] = []
    word_res = {w: re.compile(rf"\b{re.escape(w)}\b") for w in FORBIDDEN_WORDS}

    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIX or not path.is_file():
            continue
        if path.name == "check-pii.py":
            continue  # the deny-list itself
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(ROOT).as_posix()

        if "/fixtures/" in rel and rel not in REVIEWED_FIXTURES:
            if sum(bool(rx.search(text)) for rx in FEED_SHAPE) >= 2:
                findings.append(
                    f"{rel}: looks like a captured API response and is not in "
                    "REVIEWED_FIXTURES — read it end to end, then add it there"
                )

        for n, line in enumerate(text.splitlines(), 1):
            if ALLOW_LINE.search(line):
                continue
            for term in FORBIDDEN:
                if term in line:
                    findings.append(f"{rel}:{n}: real-world identifier {term!r}")
            for term, rx in word_res.items():
                if rx.search(line):
                    findings.append(f"{rel}:{n}: real-world identifier {term!r}")

    if findings:
        print("Personal data found. This repository is public.\n")
        for f in findings:
            print(f"  {f}")
        print(
            "\nUse the fictional vocabulary the tests already share: Sapphire Visa,"
            "\nHarborstone, Cascade Point HYSA, Northwind Payserv, Jane Doe. Rescale"
            "\namounts — a comment teaches with the ratio, never the digits."
        )
        return 1

    print("No personal data found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
