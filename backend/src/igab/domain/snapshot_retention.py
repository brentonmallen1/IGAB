"""Which automatic snapshots to delete.

A schedule that never prunes fills the volume, and a prune that is too eager
deletes the copy someone was relying on. The rule is small and the whole of
it is worth stating out loud, because it deletes files:

**Only snapshots the schedule itself wrote are ever pruned.** A snapshot a
person asked for is theirs — they took it before a risky import, or to hand
to someone, and nothing about a retention count applies to it. A rule that
counted both together would quietly delete a person's own copy to make room
for an automatic one, which is the opposite of what a backup is for.

**Newest first, by the name's own timestamp.** The filename carries a sortable
UTC stamp, so ordering does not depend on mtime — a file copied off the volume
and back, or restored from a tarball, keeps its place. Ties (two snapshots in
the same second) fall back to the name, so the order is total and the same
file is pruned on every run rather than the choice flapping.

Pure: a list of names in, a list of names out. Nothing here touches a disk.
"""

from collections.abc import Iterable

from igab.services.budget_snapshot import is_scheduled_snapshot


def to_prune(names: Iterable[str], keep_count: int) -> list[str]:
    """The scheduled snapshots to delete, oldest first.

    `keep_count` is how many automatic snapshots to keep. Zero or negative
    keeps them all rather than deleting everything: a misconfigured or
    unparsed setting must not be a mass delete, and "off" is expressed by
    turning the schedule off, not by a retention of nothing.
    """
    if keep_count <= 0:
        return []
    scheduled = sorted((n for n in names if is_scheduled_snapshot(n)), reverse=True)
    return sorted(scheduled[keep_count:])
