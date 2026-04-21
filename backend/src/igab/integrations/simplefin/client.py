import base64
from datetime import UTC, datetime

import httpx


class SimpleFINClient:
    """Thin async wrapper around the SimpleFIN Bridge API."""

    async def claim_access_url(self, setup_token: str) -> str:
        """Exchange a setup token for an access URL."""
        decoded = base64.b64decode(setup_token).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(decoded)
            resp.raise_for_status()
            return resp.text.strip()

    async def get_accounts(self, access_url: str) -> list[dict]:
        accounts_url = access_url.rstrip("/") + "/accounts"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(accounts_url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("accounts", [])

    async def get_transactions(
        self,
        access_url: str,
        since: datetime | None = None,
    ) -> list[dict]:
        params = {}
        if since:
            params["start-date"] = int(since.replace(tzinfo=UTC).timestamp())

        accounts_url = access_url.rstrip("/") + "/accounts"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(accounts_url, params=params)
            resp.raise_for_status()
            data = resp.json()

        transactions = []
        for account in data.get("accounts", []):
            acct_id = account.get("id")
            for txn in account.get("transactions", []):
                transactions.append({**txn, "account_id": acct_id})
        return transactions
