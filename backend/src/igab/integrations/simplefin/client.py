import base64
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimpleFINError:
    """One entry from the response's `errlist`.

    The Bridge's own guide says "Always show those errors to your end users",
    and for nine days this app did the opposite: it parsed them, logged them
    at WARNING into a root logger nothing had configured, and displayed
    nothing. `con.auth` ("Auth required") is the one that matters most — it
    names an institution whose link has lapsed, and it is per-account.
    """

    code: str
    message: str
    #: The Bridge's institution-connection id, when the error names one.
    connection_id: str | None = None

    @property
    def needs_auth(self) -> bool:
        return self.code == "con.auth"


@dataclass
class SimpleFINFeed:
    """One `/accounts` fetch: the transactions in the window, the balance
    the bank reported for each account (keyed by SimpleFIN account id), the
    name it gave each account, and any errors it reported.
    All come from the same response — a second request would double the
    hit against the bridge's rate limit for data it already sent."""

    transactions: list[dict]
    balances: dict[str, Decimal] = field(default_factory=dict)
    #: SimpleFIN account id -> the name the bank reports for it. What an
    #: orphaned link is matched against when suggesting a replacement.
    account_names: dict[str, str] = field(default_factory=dict)
    errors: list[SimpleFINError] = field(default_factory=list)


def _parse_errors(data: dict) -> list["SimpleFINError"]:
    """Read the response's errors, new spelling first.

    Protocol v2 replaced the flat `errors` array of display strings with
    structured `errlist` entries carrying a code. Both may appear — the
    Bridge's own docs still reference each in different sections — so the
    structured list wins and the legacy one fills in only when it is all
    there is.
    """
    errlist = data.get("errlist")
    if isinstance(errlist, list) and errlist:
        parsed = []
        for entry in errlist:
            if not isinstance(entry, dict):
                parsed.append(SimpleFINError(code="gen.unknown", message=str(entry)))
                continue
            parsed.append(
                SimpleFINError(
                    code=str(entry.get("code") or "gen.unknown"),
                    message=str(entry.get("msg") or entry.get("message") or ""),
                    connection_id=entry.get("conn_id"),
                )
            )
        return parsed
    legacy = data.get("errors")
    if isinstance(legacy, list):
        return [SimpleFINError(code="gen.unknown", message=str(e)) for e in legacy if e]
    return []


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

        errors = _parse_errors(data)
        if errors:
            logger.warning(
                "simplefin: bridge reported %d error(s): %s",
                len(errors),
                "; ".join(f"{e.code}: {e.message}" for e in errors),
            )

        transactions = []
        balances: dict[str, Decimal] = {}
        account_names: dict[str, str] = {}
        for account in data.get("accounts", []):
            acct_id = account.get("id")
            name = account.get("name")
            if acct_id and name:
                account_names[acct_id] = str(name)
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
        return SimpleFINFeed(
            transactions=transactions,
            balances=balances,
            account_names=account_names,
            errors=errors,
        )
