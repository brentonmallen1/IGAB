"""Transaction matching service.

Finds manually entered transactions that likely correspond to newly synced
transactions and creates a link between them.  When confidence is high
enough the link is auto-accepted; otherwise it is stored as "pending" for
human review.
"""

import uuid
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Transaction
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_match_repo import TransactionMatchRepository
from igab.repositories.transaction_repo import TransactionRepository

AUTO_ACCEPT_THRESHOLD = 0.90
DATE_WINDOW_DAYS = 3


def _payee_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    # Partial-match bonus: if one contains the other
    if a in b or b in a:
        return 0.85
    return SequenceMatcher(None, a, b).ratio()


def _date_score(synced: date, manual: date) -> float:
    """1.0 for same day, decays linearly to 0 at DATE_WINDOW_DAYS+1."""
    delta = abs((synced - manual).days)
    if delta == 0:
        return 1.0
    if delta > DATE_WINDOW_DAYS:
        return 0.0
    return 1.0 - (delta / (DATE_WINDOW_DAYS + 1))


def _amount_score(synced: Decimal, manual: Decimal) -> float:
    if manual == 0:
        return 1.0 if synced == 0 else 0.0
    diff_pct = abs((synced - manual) / manual)
    if diff_pct == 0:
        return 1.0
    if diff_pct > Decimal("0.01"):
        return 0.0
    return float(1 - diff_pct * 100)


def calculate_confidence(
    synced_amount: Decimal,
    synced_date: date,
    synced_payee: str,
    manual_amount: Decimal,
    manual_date: date,
    manual_payee: str,
) -> float:
    amount = _amount_score(synced_amount, manual_amount) * 0.4
    dt = _date_score(synced_date, manual_date) * 0.3
    payee = _payee_similarity(synced_payee, manual_payee) * 0.3
    return round(amount + dt + payee, 4)


class TransactionMatchingService:
    def __init__(
        self,
        session: AsyncSession,
        txn_repo: TransactionRepository,
        match_repo: TransactionMatchRepository,
        payee_repo: PayeeRepository,
    ) -> None:
        self.session = session
        self.txn_repo = txn_repo
        self.match_repo = match_repo
        self.payee_repo = payee_repo

    async def try_match(self, synced_txn: Transaction) -> None:
        """Attempt to find and link a manually entered transaction to a synced one."""
        candidates = await self.txn_repo.find_match_candidates(
            synced_txn.account_id,
            synced_txn.amount,
            synced_txn.date,
        )
        if not candidates:
            return

        synced_payee_name = ""
        if synced_txn.payee_id:
            p = await self.payee_repo.get(synced_txn.payee_id)
            if p:
                synced_payee_name = p.name

        best_candidate: Transaction | None = None
        best_score = 0.0

        for candidate in candidates:
            manual_payee_name = ""
            if candidate.payee_id:
                p = await self.payee_repo.get(candidate.payee_id)
                if p:
                    manual_payee_name = p.name

            score = calculate_confidence(
                synced_txn.amount,
                synced_txn.date,
                synced_payee_name,
                candidate.amount,
                candidate.date,
                manual_payee_name,
            )
            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate is None or best_score < 0.5:
            return

        status = "accepted" if best_score >= AUTO_ACCEPT_THRESHOLD else "pending"

        await self.match_repo.create(
            synced_transaction_id=synced_txn.id,
            manual_transaction_id=best_candidate.id,
            confidence_score=best_score,
            status=status,
        )

        if status == "accepted":
            await self._accept_link(synced_txn, best_candidate, best_score)

    async def _accept_link(
        self,
        synced_txn: Transaction,
        manual_txn: Transaction,
        confidence: float,
    ) -> None:
        """Accept match: copy sync metadata to manual, soft-delete synced."""
        await self.session.execute(
            update(Transaction)
            .where(Transaction.id == manual_txn.id)
            .values(
                import_id=synced_txn.import_id,
                import_description=synced_txn.import_description,
                has_sync_source=True,
            )
        )
        await self.session.execute(
            update(Transaction)
            .where(Transaction.id == synced_txn.id)
            .values(is_deleted=True)
        )
        await self.session.flush()

    async def accept_match(self, match_id: uuid.UUID) -> None:
        match = await self.match_repo.get(match_id)
        if match is None or match.status == "accepted":
            return
        await self.match_repo.update_status(match_id, "accepted")
        from sqlalchemy import select

        synced = (
            await self.session.execute(
                select(Transaction).where(Transaction.id == match.synced_transaction_id)
            )
        ).scalar_one()
        manual = (
            await self.session.execute(
                select(Transaction).where(Transaction.id == match.manual_transaction_id)
            )
        ).scalar_one()
        await self._accept_link(synced, manual, float(match.confidence_score))

    async def reject_match(self, match_id: uuid.UUID) -> None:
        await self.match_repo.update_status(match_id, "rejected")


def _best_payee_id(synced: Transaction, manual: Transaction) -> uuid.UUID | None:
    """Prefer the manual payee (user-cleaned name) over the raw synced payee."""
    return manual.payee_id or synced.payee_id
