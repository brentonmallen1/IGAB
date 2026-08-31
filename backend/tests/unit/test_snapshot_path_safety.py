"""A client's string chooses among files we listed; it never builds a path.

CodeQL's `py/path-injection` flags nine sites across `backup_service`,
`budget_snapshot` and the snapshot routes, and the docstrings there already
answer it: the guarantee is control flow, not a validator. A name that arrived
over HTTP is checked for shape, then must MATCH AN ENTRY THE SERVER SCANNED,
and only that entry's name is joined onto the base.

Nothing tested it. That matters more than usual here, because the shape check
on its own is *not* sufficient — see `test_the_shape_check_alone_is_not_the
_defence` — so a future reader who believes it is could delete the listing
lookup and leave the docstring behind. These are what makes the claim a
mechanism.
"""

import os
from pathlib import Path

import pytest

from igab.domain.exceptions import InvariantViolation
from igab.services.backup_service import listed_backup_path, safe_backup_filename
from igab.services.budget_snapshot import slugify

#: Separators, traversal, absolute paths, nulls, and the empty-ish cases. On
#: POSIX an absolute component is worse than "..": joining one discards the
#: base entirely rather than walking up from it.
HOSTILE = [
    "../../../../etc/passwd",
    "/etc/passwd",
    "/",
    "..",
    ".",
    "....//evil",
    "a/b/../../../c.igab",
    "snap.igab/../../../etc/x",
    "..\\..\\windows\\system32",
    "x\x00.igab",
    ".hidden",
    "",
    "   ",
]


@pytest.mark.parametrize("hostile", HOSTILE)
def test_a_name_that_could_leave_its_directory_is_refused(hostile):
    with pytest.raises(InvariantViolation):
        safe_backup_filename(hostile)


@pytest.mark.parametrize("ordinary", ["budget-20260830-120000.igab", "igab-backup.sql.gz"])
def test_an_ordinary_name_survives(ordinary):
    assert safe_backup_filename(ordinary) == ordinary


@pytest.mark.parametrize("sneaky", ["%2e%2e%2fetc%2fpasswd", "‮.igab"])
def test_the_shape_check_alone_is_not_the_defence(sneaky):
    """These two pass `safe_backup_filename`, and that is fine — but only
    because of what happens next.

    Percent-encoded traversal is a single path component to a filesystem, and
    Starlette has already decoded the URL once, so a real `%2e%2e%2f` in a
    request arrives as `../` and is refused above. A right-to-left override is
    a display trick, not a separator.

    Neither can reach a file, because the caller must then find the name in a
    directory scan — and no such file can exist, since every snapshot this app
    writes is named by `slugify`. Delete that lookup and these become live.
    """
    assert safe_backup_filename(sneaky) == sneaky
    assert "/" not in sneaky.encode("unicode_escape").decode().replace("%2f", "")


@pytest.mark.parametrize(
    "budget_name",
    HOSTILE + ["../../etc", "..%2f..%2f", "‮evil"],
)
def test_a_hostile_budget_name_cannot_shape_the_file_it_is_saved_as(budget_name):
    """The other direction, and the one a validator cannot cover: the file
    name is built from the budget's own name, which a user types.

    `snapshot_filename` slugs it, so no separator, dot-segment or null
    survives to reach `directory / …`.
    """
    slug = slugify(budget_name)
    assert "/" not in slug and "\\" not in slug and "\x00" not in slug
    assert slug not in ("", ".", "..")
    assert not slug.startswith(".")
    assert (Path("/data/snapshots") / f"{slug}.igab").parent == Path("/data/snapshots")


class TestTheListedPathIsTheRealGuarantee:
    def test_a_file_inside_the_directory_resolves(self, tmp_path):
        base = tmp_path / "snapshots"
        base.mkdir()
        (base / "good.igab").write_text("x")
        assert listed_backup_path(base, "good.igab") == (base / "good.igab").resolve()

    def test_a_symlink_planted_inside_cannot_reach_out(self, tmp_path):
        """What a directory listing cannot rule out on its own.

        `scandir` reports the symlink, its name passes every pattern, and only
        resolving both sides catches it — which is why the containment check
        stays even though the name came from a scan.
        """
        base = tmp_path / "snapshots"
        base.mkdir()
        secret = tmp_path / "outside.txt"
        secret.write_text("secret")
        os.symlink(secret, base / "innocent.igab")

        with pytest.raises(InvariantViolation):
            listed_backup_path(base, "innocent.igab")
