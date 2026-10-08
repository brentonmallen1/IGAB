"""A SimpleFIN bridge that answers from a fixed payload, for sync tests.

One fake for every suite that drives `SimpleFINService` against the real
database. There were four, each with its own subset of the protocol, and none
of them could see the `account=` filter — so when the service started naming
accounts, three of them would have answered a filtered request with every
account and the tests would have kept passing. This one answers the way the
bridge does, and keeps every request so a test can assert on what was asked
rather than only on what came back.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from igab.integrations.simplefin.client import SimpleFINError, SimpleFINFeed


@dataclass(frozen=True)
class BridgeRequest:
    """One `/accounts` request as the bridge saw it."""

    since: datetime | None
    #: None when the request named no account — an all-accounts request.
    account_ids: tuple[str, ...] | None


class FakeBridge:
    """Answers `get_feed` from `payload`, filtered like the real bridge.

    - `account_ids` narrows the answer to those accounts: rows, balances,
      names and dates alike. An id the bridge does not know comes back as
      nothing at all, which is what a reissued id looks like from the side
      that still holds the old one, plus an `act.failed` entry in the
      errlist. That is the real bridge's answer, probed 2026-10-07: HTTP 200,
      `accounts: []`, and `{"code": "act.failed", "msg": "Unable to fetch
      account ID: <id>", "account_id": "<id>"}`, not an HTTP error.
    - `honour_window` drops rows posted before `since`, which is the only way
      to test that a window was wide enough.
    """

    def __init__(
        self,
        payload: Sequence[dict] = (),
        balances: dict[str, Decimal] | None = None,
        *,
        names: dict[str, str] | None = None,
        errors: Sequence[SimpleFINError] = (),
        balance_dates: dict[str, datetime] | None = None,
        honour_window: bool = False,
    ) -> None:
        self.payload = list(payload)
        self.balances = balances if balances is not None else {}
        self.names = names if names is not None else {}
        self.errors = list(errors)
        self.balance_dates = balance_dates if balance_dates is not None else {}
        self.honour_window = honour_window
        self.requests: list[BridgeRequest] = []
        self.listings = 0

    async def get_feed(
        self,
        access_url: str,
        since: datetime | None = None,
        account_ids: Sequence[str] | None = None,
    ) -> SimpleFINFeed:
        named = tuple(account_ids) if account_ids else None
        self.requests.append(BridgeRequest(since=since, account_ids=named))

        def served(account_id: str | None) -> bool:
            return named is None or account_id in named

        rows = [t for t in self.payload if served(t.get("account_id"))]
        if self.honour_window and since is not None:
            rows = [t for t in rows if t["posted"] >= since.timestamp()]
        return SimpleFINFeed(
            transactions=rows,
            balances={k: v for k, v in self.balances.items() if served(k)},
            balance_dates={k: v for k, v in self.balance_dates.items() if served(k)},
            account_names={k: v for k, v in self.names.items() if served(k)},
            errors=[*self.errors, *self._unknown(named)],
        )

    def _unknown(self, named: tuple[str, ...] | None) -> list[SimpleFINError]:
        """The bridge's `act.failed` for each named id it has no account for."""
        if named is None:
            return []
        known = set(self.names) | set(self.balances) | {t.get("account_id") for t in self.payload}
        return [
            SimpleFINError(code="act.failed", message=f"Unable to fetch account ID: {a}")
            for a in named
            if a not in known
        ]

    async def get_accounts(self, access_url: str) -> list[dict]:
        self.listings += 1
        return [{"id": account_id, "name": name} for account_id, name in self.names.items()]

    @property
    def filters(self) -> list[tuple[str, ...] | None]:
        """What each request named, in order — None for all accounts."""
        return [r.account_ids for r in self.requests]
