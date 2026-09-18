"""What the retention rule deletes, and what it must never touch.

These are assertions about deleting files, so the cases that must NOT be
pruned carry as much weight as the ones that must.
"""

from igab.domain.snapshot_retention import to_prune
from igab.services.budget_snapshot import is_scheduled_snapshot, snapshot_filename

AUTO = [
    "household-20260901-020000-auto.igab.zip",
    "household-20260902-020000-auto.igab.zip",
    "household-20260903-020000-auto.igab.zip",
]
MINE = "household-20260815-134500.igab.zip"


class TestWhatIsPruned:
    def test_the_oldest_scheduled_snapshots_go(self):
        assert to_prune(AUTO, 2) == [AUTO[0]]

    def test_keeping_more_than_exist_prunes_nothing(self):
        assert to_prune(AUTO, 10) == []

    def test_it_returns_oldest_first(self):
        assert to_prune(AUTO, 1) == [AUTO[0], AUTO[1]]


class TestWhatIsNeverPruned:
    def test_a_persons_own_snapshot_is_never_touched(self):
        """Theirs, taken before a risky import or to hand to someone. A rule
        that counted both together would delete it to make room for an
        automatic one, which is the opposite of what a backup is for."""
        assert MINE not in to_prune([MINE, *AUTO], 1)

    def test_a_manual_snapshot_does_not_count_toward_the_allowance(self):
        # Three automatic, keep two: exactly one goes, whatever else is there.
        assert to_prune([MINE, *AUTO], 2) == [AUTO[0]]

    def test_a_retention_of_zero_keeps_everything(self):
        """A misconfigured or unparsed setting must not be a mass delete.
        'Off' is expressed by turning the schedule off."""
        assert to_prune(AUTO, 0) == []
        assert to_prune(AUTO, -1) == []

    def test_an_empty_folder_is_fine(self):
        assert to_prune([], 3) == []


class TestOrderingIsStable:
    def test_order_comes_from_the_name_not_the_filesystem(self):
        """The name carries a sortable UTC stamp, so a file copied off the
        volume and back keeps its place — mtime would not."""
        shuffled = [AUTO[2], AUTO[0], AUTO[1]]
        assert to_prune(shuffled, 1) == [AUTO[0], AUTO[1]]

    def test_two_in_the_same_second_are_ordered_by_name(self):
        same = [
            "household-20260901-020000-auto.igab.zip",
            "harborstone-20260901-020000-auto.igab.zip",
        ]
        # Total order, so the same file is pruned on every run rather than
        # the choice flapping between them.
        assert to_prune(same, 1) == to_prune(list(reversed(same)), 1)


class TestTheMarker:
    def test_the_builder_and_the_predicate_agree(self):
        """One spelling. Retention deletes on this answer, and a second
        reading of the same name is how a person's snapshot gets deleted."""
        assert is_scheduled_snapshot(snapshot_filename("Household", scheduled=True))
        assert not is_scheduled_snapshot(snapshot_filename("Household"))

    def test_a_budget_named_auto_is_not_mistaken_for_one(self):
        """The marker sits before the suffix, not anywhere in the name."""
        assert not is_scheduled_snapshot(snapshot_filename("Auto Loan Budget"))
