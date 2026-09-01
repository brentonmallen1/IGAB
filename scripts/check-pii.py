#!/usr/bin/env python3
"""Refuse to ship personal data. Runs first in `just ci`; run it before you commit.

This repository is public, and it has already leaked once: a captured bank-feed
response with 250 real transactions — two people's names, a mortgage account
number, a student loan number, a life insurance policy number, a medical
payment plan. It went in under a sanitizer whose docstring promised to strip
names and whose code had no name handling at all, and no test ever loaded the
file. Prose did not stop it. This is the mechanism that does.

**The deny-list is hashed, and that is not decoration.** A plaintext list of
the exact strings you must never publish is itself a list of the exact strings
you must never publish — the first version of this file leaked six of them into
the very commit that added the check. Hashes also survive a history rewrite: a
`--replace-text` pass edits plaintext, so the earlier list came out the far side
denying the *fictional* names and waving the real ones through.

Add a term with `--add "Some Name"`, which prints the digest and nothing else.

Two checks:

1. **Terms that must never appear**, matched on word and word-pair boundaries
   so `Doe` is caught and `brentonmallen1/IGAB` — the project's own public URL —
   is not. Add to the list whenever a real one is found and removed; it is a
   ratchet, and the only part of this that knows what your real data looks like.

2. **Captured API responses.** The leak was one. Any JSON under a fixtures
   directory carrying transaction shape must be named in `REVIEWED_FIXTURES` —
   a line someone can only add after opening the file, which is the step that
   did not happen.

A digit-run heuristic was written here and deleted before committing: it fired
a hundred times on UUIDs, on `1234567890`, on dates, on `99999999999999`. A
check that cries wolf is a check someone disables, and then there is none.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Single distinctive words. Deliberately no generic ones: an insurer whose
#: first word is also a UI element in this codebase would fire on every file
#: that renders one, so names like that live in BIGRAMS instead.
UNIGRAMS = {
    "2ad55da5b6ea629b", "2bf666b1b50b373e", "3bb8d0201f179959", "413e4cbd79004f0b",
    "4f74a33966da3f01", "5aea8a5f9b55fb47", "61ced68c200cbde9", "681a024a50310b7d",
    "973e809e7e7f3e46", "978d2a2dd71d5d71", "9c58d15eceb3e456", "9c8720f7f1528d3e",
    "a0e25391d8319bab", "b9805963ecf02918", "bdafd7b1ab8272c5", "c4aee9e4b5773431",
    "abbecdcda8407880", "c5d673cfa1ad5d6f", "e23011c058a38a17", "f66f87d87754f4a7",
}
#: Adjacent word pairs, for names whose halves are each too common to deny.
BIGRAMS = {
    "09d162fa55b1db96", "1a7d0ae5fd57c70b", "1c4f30b2571bff36", "30e6e59dae1afedc",
    "6e8af52a4fc562ba", "7b8fce79d7683357", "9ecfbcd384d94894", "bcb7efe2c01e5f56",
}
#: Account, loan, policy and payment reference numbers.
NUMBERS = {
    "1ab7df26727809d7", "1b8d25774ca4af3c", "42385c83276e3025", "6d4281aba941bc6c",
    "83482529e2f2c243", "9b83e8c348499f82", "a3af7a88d95db049", "d5c31b03e34e140b",
    "f3e1adb04a196f16",
}

#: Fixture files read end to end and known to be fiction. Adding a line here is
#: the review; do not add one for a file you have not opened.
REVIEWED_FIXTURES = {
    "backend/tests/fixtures/ynab/Parity Budget - Plan.csv",
    "backend/tests/fixtures/ynab/Parity Budget - Register.csv",
}

#: A saved bank feed, by shape rather than by name.
FEED_SHAPE = (
    re.compile(r'"description"\s*:'),
    re.compile(r'"posted"\s*:'),
    re.compile(r'"payee"\s*:'),
)

WORD = re.compile(r"[a-z]{3,}")
NUMBER = re.compile(r"\d{6,}")
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2")


def digest(term: str) -> str:
    return hashlib.sha256(term.strip().lower().encode()).hexdigest()[:16]


def offences(line: str) -> list[str]:
    words = WORD.findall(line.lower())
    found = [w for w in words if digest(w) in UNIGRAMS]
    found += [
        f"{a} {b}" for a, b in zip(words, words[1:]) if digest(f"{a} {b}") in BIGRAMS
    ]
    found += [n for n in NUMBER.findall(line) if digest(n) in NUMBERS]
    return found


def read_text(path: Path) -> str | None:
    """The searchable text of a file, including inside a zip.

    A fixture that is an archive would otherwise slip the whole check: a zip
    does not decode as UTF-8, so it was skipped, and "never commit a captured
    response you have not read" had nothing enforcing it for exactly the shape
    most likely to carry one. Members that are not text are skipped
    individually rather than disqualifying the archive.
    """
    if path.suffix.lower() == ".zip":
        parts: list[str] = []
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    parts.append(name)
                    try:
                        parts.append(archive.read(name).decode("utf-8"))
                    except (UnicodeDecodeError, KeyError):
                        continue
        except zipfile.BadZipFile:
            return None
        return "\n".join(parts)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [ROOT / p.decode() for p in out.split(b"\0") if p]


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--add":
        print(f'  "{digest(argv[2])}",   # add to UNIGRAMS / BIGRAMS / NUMBERS')
        return 0

    findings: list[str] = []
    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIX or not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = read_text(path)
        except OSError:
            continue
        if text is None:
            continue

        if "/fixtures/" in rel and rel not in REVIEWED_FIXTURES:
            if sum(bool(rx.search(text)) for rx in FEED_SHAPE) >= 2:
                findings.append(
                    f"{rel}: looks like a captured API response and is not in "
                    "REVIEWED_FIXTURES — read it end to end, then add it there"
                )

        for n, line in enumerate(text.splitlines(), 1):
            for term in offences(line):
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
    raise SystemExit(main(sys.argv))
