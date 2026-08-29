import base64
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SimpleFINFeed:
    """One `/accounts` fetch: the transactions in the window, and the balance
    the bank reported for each account (keyed by SimpleFIN account id).
    Both come from the same response — a second request would double the
    hit against the bridge's rate limit for data it already sent."""

    transactions: list[dict]
    balances: dict[str, Decimal] = field(default_factory=dict)


def _extract_auth(access_url: str) -> tuple[str, tuple[str, str]]:
    """Split access_url into (bare_url, (username, password)).

    SimpleFIN returns URLs like https://user:pass@bridge.simplefin.org/simplefin.
    httpx doesn't always forward embedded credentials on redirects, so we
    extract them and pass auth explicitly.
    """
    parsed = urlparse(access_url)
    bare_url = parsed._replace(netloc=parsed.hostname or "").geturl()
    if parsed.port:
        bare_url = parsed._replace(netloc=f"{parsed.hostname}:{parsed.port}").geturl()
    username = parsed.username or ""
    password = parsed.password or ""
    return bare_url, (username, password)


class SimpleFINClient:
    """Thin async wrapper around the SimpleFIN Bridge API."""

    async def claim_access_url(self, setup_token: str) -> str:
        """Exchange a setup token for an access URL.

        The setup token is a URL-safe base64-encoded claim URL. We POST to it
        with an empty body (Content-Length: 0) to receive the access URL.
        """
        # URL-safe base64 with padding normalisation
        token = setup_token.strip()
        padding = 4 - len(token) % 4
        if padding != 4:
            token += "=" * padding
        try:
            claim_url = base64.urlsafe_b64decode(token).decode()
        except Exception as exc:
            logger.error("Failed to base64-decode setup token: %s", exc)
            raise ValueError(f"Invalid setup token (base64 decode failed): {exc}") from exc

        logger.info("Claiming SimpleFIN access URL from: %s", claim_url[:60])
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                claim_url,
                content=b"",
                headers={"Content-Length": "0"},
            )
            logger.info("Claim response status: %s", resp.status_code)
            if not resp.is_success:
                logger.error("Claim failed — status %s body: %s", resp.status_code, resp.text[:200])
            resp.raise_for_status()
            access_url = resp.text.strip()
            logger.info("Received access URL (masked): %s...%s", access_url[:20], access_url[-10:])
            return access_url

    async def get_accounts(self, access_url: str) -> list[dict]:
        bare_url, auth = _extract_auth(access_url)
        accounts_url = bare_url.rstrip("/") + "/accounts"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(accounts_url, auth=auth, params={"version": "2"})
            resp.raise_for_status()
            data = resp.json()
            return data.get("accounts", [])

    async def get_feed(
        self,
        access_url: str,
        since: datetime | None = None,
    ) -> "SimpleFINFeed":
        """One `/accounts` request: the window's transactions AND each
        account's reported balance. The balance rides in the same response —
        discarding it (as the old `get_transactions` did) is how a first
        sync's 90-day window shipped a ledger thousands short of what the
        bank said, with nothing anchoring the difference."""
        bare_url, auth = _extract_auth(access_url)
        params: dict[str, str | int] = {"version": "2", "pending": "1"}
        if since:
            params["start-date"] = int(since.replace(tzinfo=UTC).timestamp())

        accounts_url = bare_url.rstrip("/") + "/accounts"
        logger.info("Fetching SimpleFIN transactions from %s with params %s", accounts_url, params)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(accounts_url, auth=auth, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("errors"):
            logger.warning("SimpleFIN errlist: %s", data["errors"])

        transactions = []
        balances: dict[str, Decimal] = {}
        for account in data.get("accounts", []):
            acct_id = account.get("id")
            raw_balance = account.get("balance")
            if acct_id and raw_balance is not None:
                try:
                    # The posted balance — pending activity is in
                    # "available-balance", which the ledger also excludes.
                    balances[acct_id] = Decimal(str(raw_balance))
                except (InvalidOperation, ValueError):
                    logger.warning("Unparseable SimpleFIN balance %r for %s", raw_balance, acct_id)
            for txn in account.get("transactions", []):
                transactions.append({**txn, "account_id": acct_id})
        return SimpleFINFeed(transactions=transactions, balances=balances)
