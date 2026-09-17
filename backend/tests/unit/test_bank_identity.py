"""The detector for a bank that re-issued its account identifier.

Named for the incident it prevents: an account that went nine days importing
nothing because its `ACT-…` changed. The row-level half — adopting re-issued
transaction ids instead of duplicating the history — is a SQL predicate,
covered in tests/integration/test_simplefin_reidentification.py.
"""

import uuid

from igab.domain.bank_identity import FeedAccount, LinkedAccount, audit_links


class TestAuditLinks:
    def _account(
        self, name="Harborstone Checking", sf_id="ACT-old", known_as="HARBORSTONE EVERYDAY CHECKING"
    ):
        return LinkedAccount(
            id=uuid.uuid4(),
            name=name,
            simplefin_account_id=sf_id,
            simplefin_account_name=known_as,
        )

    def test_stored_id_absent_from_feed_is_orphaned(self):
        """The nine-day outage: the account still looks linked and still syncs."""
        account = self._account()
        audit = audit_links(
            linked=[account],
            feed=[FeedAccount(id="ACT-new", name="HARBORSTONE EVERYDAY CHECKING", txn_count=132)],
        )
        assert not audit.clean
        assert audit.orphaned[0].account_id == account.id
        assert audit.orphaned[0].stored_simplefin_id == "ACT-old"

    def test_same_name_feed_account_is_suggested(self):
        audit = audit_links(
            linked=[self._account()],
            feed=[FeedAccount(id="ACT-new", name="HARBORSTONE EVERYDAY CHECKING", txn_count=132)],
        )
        assert audit.orphaned[0].suggested_feed_id == "ACT-new"

    def test_matches_the_bank_string_not_the_user_rename(self):
        """ "Harborstone Checking" resembles nothing the bank says; the name stored at
        link time is what identifies the account."""
        audit = audit_links(
            linked=[
                self._account(name="Harborstone Checking", known_as="HARBORSTONE EVERYDAY CHECKING")
            ],
            feed=[FeedAccount(id="ACT-new", name="HARBORSTONE EVERYDAY CHECKING")],
        )
        assert audit.orphaned[0].suggested_feed_id == "ACT-new"

    def test_near_tie_suggests_nothing(self):
        """Two cards at one bank read almost alike. A prefilled wrong relink
        files one account's transactions into another."""
        audit = audit_links(
            linked=[self._account(known_as="Sapphire Visa Signature Rewards")],
            feed=[
                FeedAccount(id="ACT-a", name="Sapphire Visa Signature Rewards Plus"),
                FeedAccount(id="ACT-b", name="Sapphire Visa Signature Rewards Plan"),
            ],
        )
        assert audit.orphaned[0].suggested_feed_id is None

    def test_unrelated_candidate_suggests_nothing(self):
        audit = audit_links(
            linked=[self._account(known_as="HARBORSTONE EVERYDAY CHECKING")],
            feed=[FeedAccount(id="ACT-x", name="Cascade Point Roth IRA")],
        )
        assert audit.orphaned[0].suggested_feed_id is None

    def test_healthy_links_are_clean(self):
        account = self._account(sf_id="ACT-live")
        audit = audit_links(
            linked=[account],
            feed=[FeedAccount(id="ACT-live", name="HARBORSTONE EVERYDAY CHECKING")],
        )
        assert audit.clean
        assert audit.unclaimed == []

    def test_unclaimed_feed_accounts_are_reported(self):
        """A feed account nothing points at — either never linked, or the
        other half of an orphaning."""
        audit = audit_links(
            linked=[self._account(sf_id="ACT-live")],
            feed=[
                FeedAccount(id="ACT-live", name="HARBORSTONE EVERYDAY CHECKING"),
                FeedAccount(id="ACT-other", name="Brokerage - Non-retirement", txn_count=2),
            ],
        )
        assert audit.clean
        assert [u.feed_id for u in audit.unclaimed] == ["ACT-other"]
        assert audit.unclaimed[0].txn_count == 2

    def test_an_orphan_is_never_suggested_a_claimed_account(self):
        """The suggestion pool is unclaimed accounts only — otherwise two
        accounts would be pointed at one bank account."""
        live = LinkedAccount(
            id=uuid.uuid4(),
            name="Other",
            simplefin_account_id="ACT-live",
            simplefin_account_name="HARBORSTONE EVERYDAY CHECKING",
        )
        audit = audit_links(
            linked=[self._account(sf_id="ACT-old"), live],
            feed=[FeedAccount(id="ACT-live", name="HARBORSTONE EVERYDAY CHECKING")],
        )
        assert audit.orphaned[0].suggested_feed_id is None
