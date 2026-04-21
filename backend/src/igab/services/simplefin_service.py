import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import SimpleFINConnection
from igab.integrations.simplefin.client import SimpleFINClient
from igab.integrations.simplefin.encryption import decrypt, encrypt
from igab.repositories.account_repo import AccountRepository
from igab.repositories.simplefin_repo import SimpleFINRepository
from igab.repositories.transaction_repo import TransactionRepository
from igab.services.transaction_service import TransactionCreate, TransactionService


class SimpleFINService:
    def __init__(
        self,
        session: AsyncSession,
        repo: SimpleFINRepository,
        account_repo: AccountRepository,
        txn_repo: TransactionRepository,
        txn_service: TransactionService,
    ) -> None:
        self.session = session
        self.repo = repo
        self.account_repo = account_repo
        self.txn_repo = txn_repo
        self.txn_service = txn_service
        self.client = SimpleFINClient()

    async def setup(self, user_id: uuid.UUID, setup_token: str) -> SimpleFINConnection:
        access_url = await self.client.claim_access_url(setup_token)
        encrypted = encrypt(access_url)
        return await self.repo.create(user_id=user_id, access_url_encrypted=encrypted)

    async def list_connections(self, user_id: uuid.UUID) -> list[SimpleFINConnection]:
        return await self.repo.get_all_for_user(user_id)

    async def update_interval(
        self, connection_id: uuid.UUID, sync_interval_hours: int
    ) -> SimpleFINConnection:
        return await self.repo.update(connection_id, sync_interval_hours=sync_interval_hours)

    async def delete(self, connection_id: uuid.UUID) -> None:
        await self.repo.delete(connection_id)

    async def get_remote_accounts(self, connection_id: uuid.UUID) -> list[dict]:
        conn = await self.repo.get(connection_id)
        if conn is None:
            return []
        access_url = decrypt(conn.access_url_encrypted)
        return await self.client.get_accounts(access_url)

    async def sync(self, connection_id: uuid.UUID, budget_id: uuid.UUID) -> dict:
        conn = await self.repo.get(connection_id)
        if conn is None:
            return {"imported": 0, "skipped": 0, "error": "Connection not found"}

        access_url = decrypt(conn.access_url_encrypted)
        txns = await self.client.get_transactions(access_url, since=conn.last_sync_at)

        imported = 0
        skipped = 0
        for t in txns:
            import_id = f"sf:{t.get('id', '')}"
            acct_sf_id = t.get("account_id")
            if not acct_sf_id:
                skipped += 1
                continue

            account = await self.account_repo.get_by_simplefin_id(budget_id, acct_sf_id)
            if account is None:
                skipped += 1
                continue

            existing = await self.txn_repo.find_by_import_id(account.id, import_id)
            if existing:
                skipped += 1
                continue

            posted_ts = t.get("posted")
            transacted_ts = t.get("transacted_at")
            timestamp = posted_ts or transacted_ts
            txn_date = (
                datetime.fromtimestamp(timestamp, tz=UTC).date()
                if isinstance(timestamp, (int, float))
                else date.today()
            )
            # Transactions without a posted timestamp haven't cleared the bank yet
            cleared = "uncleared" if posted_ts else "pending"
            amount = Decimal(str(t.get("amount", "0")))

            await self.txn_service.create(
                budget_id,
                TransactionCreate(
                    account_id=account.id,
                    date=txn_date,
                    amount=amount,
                    payee_name=t.get("description", ""),
                    import_id=import_id,
                    cleared=cleared,
                    approved=False,
                ),
            )
            imported += 1

        today = date.today()
        requests_today = conn.requests_today + 1 if conn.last_request_date == today else 1
        await self.repo.update(
            connection_id,
            last_sync_at=datetime.now(tz=UTC),
            last_request_date=today,
            requests_today=requests_today,
        )
        return {"imported": imported, "skipped": skipped}
