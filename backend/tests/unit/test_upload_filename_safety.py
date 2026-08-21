"""Uploaded filenames must not be able to escape their directory.

Starlette hands back the Content-Disposition filename verbatim, so it is
attacker-controlled. The receipt upload joins it onto the staging directory and
writes to it, which makes traversal an arbitrary file write — and on POSIX an
absolute component is worse than "..", because joining one discards the base
entirely rather than walking up from it.
"""

from pathlib import Path

import pytest

from igab.api.v1.ai_jobs import _safe_filename

STAGE = Path("/data/attachments/ai_staging/0e0e0e0e-0000-0000-0000-000000000000")


@pytest.mark.parametrize(
    "hostile",
    [
        "../../../../etc/cron.d/evil",
        "/etc/passwd",
        "/",
        "..",
        ".",
        "....//evil",
        "a/b/../../../c.png",
        "",
        "   ",
        None,
    ],
)
def test_hostile_names_stay_inside_the_staging_directory(hostile):
    resolved = (STAGE / _safe_filename(hostile)).resolve()
    assert resolved.parent == STAGE, f"{hostile!r} escaped to {resolved}"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("receipt.jpg", "receipt.jpg"),
        ("Costco 2026-08-21.pdf", "Costco 2026-08-21.pdf"),
        (".hidden", ".hidden"),
        ("a/b/c.png", "c.png"),
        ("/tmp/scan.heic", "scan.heic"),
    ],
)
def test_ordinary_names_keep_their_basename(given, expected):
    assert _safe_filename(given) == expected


@pytest.mark.parametrize("empty", ["", "   ", "..", ".", "/", None])
def test_nothing_usable_falls_back_rather_than_returning_empty(empty):
    assert _safe_filename(empty) == "receipt.jpg"


def test_backslashes_are_folded_not_left_as_separators():
    # Not separators on POSIX, so they would otherwise survive into the stored
    # name and mean something different on a Windows client reading it back.
    assert "\\" not in _safe_filename("..\\..\\windows\\evil.txt")
