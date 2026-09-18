"""What the bank calls things, and what to do when it changes its mind.

A SimpleFIN Bridge connection that is re-linked mints fresh identifiers: a
new `ACT-…` for the account, and fresh ids for every transaction in it.
Nothing in the protocol announces this, and both halves of it have cost real
data:

- The account's stored `simplefin_account_id` stops appearing in the feed, so
  every row for it falls out of the sync's target check and is counted as an
  ordinary skip. An account went nine days importing nothing while reporting
  success.
- Every row then arrives with an id the register has never seen, and the
  dedup ladder cannot help: it only offers candidates with **no** bank link
  at all (`BANK_UNLINKED`), and these rows carry the *old* link. One sync
  wrote 277 duplicates of already-reconciled transactions.

`audit_links` is the detector for the first, kept pure so every branch is a
one-line test. The second is answered row by row in
`repositories.txn_filters.orphaned_link`: a row inside the fetched window
whose id the feed omits is one the bank has retired. An account-level gate
("every stored id is absent from the feed") used to live here; it failed the
first time it was needed twice, because after a partial catch-up the account
held both retired and current ids and no longer looked re-identified.
"""

import uuid
from dataclasses import dataclass

from igab.domain.matching import name_similarity

#: How alike two account names must be before one is offered as the other's
#: replacement. High on purpose: the suggestion prefills a relink, and a
#: wrong relink files one account's transactions into another.
LINK_SUGGESTION_THRESHOLD = 0.75

#: A suggestion must also beat its runner-up by this much. Two cards at the
#: same bank read almost alike ("Visa Signature ...848" / "...849"), and a
#: near-tie is exactly when a human should choose.
LINK_SUGGESTION_MARGIN = 0.10


@dataclass(frozen=True)
class LinkedAccount:
    """An account in the budget that claims a bank account."""

    id: uuid.UUID
    name: str
    simplefin_account_id: str
    #: What the feed called it when the user linked it. The better of the two
    #: names to match on — `name` is whatever the user renamed it to.
    simplefin_account_name: str | None = None


@dataclass(frozen=True)
class FeedAccount:
    """An account the feed reported in this run."""

    id: str
    name: str | None = None
    txn_count: int = 0


@dataclass(frozen=True)
class OrphanedLink:
    """A budget account whose bank link no longer resolves."""

    account_id: uuid.UUID
    account_name: str
    stored_simplefin_id: str
    suggested_feed_id: str | None = None
    suggested_feed_name: str | None = None
    suggestion_score: float = 0.0
    #: The suggestion is the *same name*, not merely a similar one, and no
    #: other unclaimed account shares it. Only this may be acted on without
    #: asking: two of one person's brokerage accounts score 0.95 against each
    #: other, so a similar name is evidence for a human and nothing more.
    suggestion_is_exact: bool = False
    #: The bridge reported an institution needing re-authentication in the
    #: same response, and nothing in the feed looks like this account. That
    #: is what a lapsed login looks like from here — the account is not gone,
    #: it is unreachable — and "relink it" would be the wrong advice.
    may_need_auth: bool = False


@dataclass(frozen=True)
class UnclaimedFeed:
    """A bank account in the feed that no budget account claims."""

    feed_id: str
    feed_name: str | None
    txn_count: int


@dataclass(frozen=True)
class LinkAudit:
    orphaned: list[OrphanedLink]
    unclaimed: list[UnclaimedFeed]

    @property
    def clean(self) -> bool:
        return not self.orphaned


def audit_links(
    *, linked: list[LinkedAccount], feed: list[FeedAccount], needs_auth: bool = False
) -> LinkAudit:
    """Reconcile the budget's bank links against what the feed actually offers.

    An orphan is paired with a suggested replacement only when one unclaimed
    feed account is both similar enough and clearly better than the next —
    the suggestion prefills a relink, so an ambiguous guess is worse than
    none. Unclaimed accounts are reported whether or not anything was
    orphaned: one may simply never have been linked.
    """
    feed_by_id = {f.id: f for f in feed}
    claimed = {a.simplefin_account_id for a in linked}

    unclaimed = [
        UnclaimedFeed(feed_id=f.id, feed_name=f.name, txn_count=f.txn_count)
        for f in feed
        if f.id not in claimed
    ]

    orphaned: list[OrphanedLink] = []
    for account in linked:
        if account.simplefin_account_id in feed_by_id:
            continue
        best, score = _best_replacement(account, unclaimed)
        exact = _exact_replacement(account, unclaimed)
        # An exact match is always also the best fuzzy one, so it leads.
        chosen = exact or best
        orphaned.append(
            OrphanedLink(
                account_id=account.id,
                account_name=account.name,
                stored_simplefin_id=account.simplefin_account_id,
                suggested_feed_id=chosen.feed_id if chosen else None,
                suggested_feed_name=chosen.feed_name if chosen else None,
                suggestion_score=1.0 if exact else score,
                suggestion_is_exact=exact is not None,
                may_need_auth=needs_auth and chosen is None,
            )
        )
    return LinkAudit(orphaned=orphaned, unclaimed=unclaimed)


def _normalized(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def _exact_replacement(
    account: LinkedAccount, candidates: list[UnclaimedFeed]
) -> UnclaimedFeed | None:
    """The one unclaimed account carrying this account's own bank name.

    The only evidence strong enough to act on unasked. A re-linked
    institution reissues the id and keeps the name, which is precisely the
    case that cost nine days; anything short of the same name is a guess, and
    a wrong relink files one account's transactions into another.

    Ambiguity disqualifies: if two unclaimed accounts share the name, nothing
    distinguishes them.
    """
    known_as = _normalized(account.simplefin_account_name)
    if not known_as:
        return None
    exact = [c for c in candidates if _normalized(c.feed_name) == known_as]
    return exact[0] if len(exact) == 1 else None


def _best_replacement(
    account: LinkedAccount, candidates: list[UnclaimedFeed]
) -> tuple[UnclaimedFeed | None, float]:
    """The one unclaimed account worth offering, or nothing.

    Scored against the name the feed used at link time when there is one —
    the user's own rename ("Harborstone Checking") rarely resembles the bank's string
    ("HARBORSTONE EVERYDAY CHECKING").

    A lone candidate still has to clear the threshold, but has no runner-up to
    beat. That is why this result may only ever be *offered*: two of one
    person's brokerage accounts score 0.95 against each other, and with one of
    them unclaimed the margin test has nothing to compare against.
    """
    if not candidates:
        return None, 0.0
    known_as = account.simplefin_account_name or account.name
    scored = sorted(
        ((c, name_similarity(known_as, c.feed_name, unknown=0.0)) for c in candidates),
        key=lambda pair: pair[1],
        reverse=True,
    )
    best, score = scored[0]
    if score < LINK_SUGGESTION_THRESHOLD:
        return None, score
    if len(scored) > 1 and score - scored[1][1] < LINK_SUGGESTION_MARGIN:
        return None, score
    return best, score
