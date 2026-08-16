"""Transaction matching service.

Finds manually entered transactions that likely correspond to newly synced
transactions and creates a link between them.  When confidence is high
enough the link is auto-accepted; otherwise it is stored as "pending" for
human review.
"""

import uuid
from datetime import date
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Transaction
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_match_repo import TransactionMatchRepository
from igab.repositories.transaction_repo import TransactionRepository

AUTO_ACCEPT_THRESHOLD = 0.90
DATE_WINDOW_DAYS = 5


SCAN_REVIEW_THRESHOLD = 0.55
SCAN_DATE_WINDOW_DAYS = 5


def _payee_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.WRatio(a.lower(), b.lower()) / 100.0


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
            exclude_id=synced_txn.id,
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
        """Merge the pair down to one row, keeping the user's transaction.

        The keeper inherits the loser's bank/import identity (sync_id is what
        prevents the next sync from re-importing the same bank transaction).
        A reconciled row always wins the keeper role; the loser is soft-deleted
        BEFORE the identity is written so the partial unique index on
        (account_id, sync_id) never sees two live rows.
        """
        from igab.domain.exceptions import InvariantViolation

        if synced_txn.id == manual_txn.id:
            return  # a transaction can never be its own duplicate
        if synced_txn.is_deleted or manual_txn.is_deleted:
            return  # stale match — one side is already gone

        synced_reconciled = synced_txn.cleared == "reconciled"
        manual_reconciled = manual_txn.cleared == "reconciled"
        if synced_reconciled and manual_reconciled:
            raise InvariantViolation(
                "Cannot merge two reconciled transactions; unreconcile one first"
            )

        keeper, loser = manual_txn, synced_txn
        if synced_reconciled:
            keeper, loser = synced_txn, manual_txn

        if keeper.sync_id and loser.sync_id and keeper.sync_id != loser.sync_id:
            raise InvariantViolation("Both transactions are linked to different bank transactions")

        updates: dict[str, object] = {"has_sync_source": True}
        if loser.sync_id and not keeper.sync_id:
            updates["sync_id"] = loser.sync_id
            updates["sync_source"] = loser.sync_source
        if loser.import_id and not keeper.import_id:
            updates["import_id"] = loser.import_id
        if loser.import_description and not keeper.import_description:
            updates["import_description"] = loser.import_description

        # The keeper's ledger date is the user's date and stays untouched —
        # budget months follow it. The bank's posted date survives as
        # provenance metadata when the loser is the bank-sourced row.
        if loser.sync_id:
            if keeper.bank_posted_date is None:
                updates["bank_posted_date"] = loser.bank_posted_date or loser.date
            if keeper.cleared in ("uncleared", "pending") and loser.cleared in (
                "cleared",
                "reconciled",
            ):
                updates["cleared"] = "cleared"

        # Delete first, then write identity — unique-index-safe ordering.
        await self.session.execute(
            update(Transaction).where(Transaction.id == loser.id).values(is_deleted=True)
        )
        await self.session.execute(
            update(Transaction).where(Transaction.id == keeper.id).values(**updates)
        )
        await self.session.flush()

    async def accept_match(self, match_id: uuid.UUID) -> None:
        match = await self.match_repo.get(match_id)
        if match is None or match.status == "accepted":
            return
        from sqlalchemy import select

        synced = (
            await self.session.execute(
                select(Transaction).where(Transaction.id == match.synced_transaction_id)
            )
        ).scalar_one_or_none()
        manual = (
            await self.session.execute(
                select(Transaction).where(Transaction.id == match.manual_transaction_id)
            )
        ).scalar_one_or_none()
        if synced is None or manual is None or synced.is_deleted or manual.is_deleted:
            await self.match_repo.update_status(match_id, "rejected")
            return
        await self._accept_link(synced, manual, float(match.confidence_score))
        await self.match_repo.update_status(match_id, "accepted")

    async def reject_match(self, match_id: uuid.UUID) -> None:
        await self.match_repo.update_status(match_id, "rejected")

    async def scan_for_duplicates(self, account_id: uuid.UUID) -> int:
        """Scan account transactions for potential duplicates.

        Candidate pairs come pre-filtered from SQL (same amount, date within
        the window); Python only scores payee similarity. Returns count of
        new matches created.
        """
        pairs = await self.txn_repo.find_duplicate_candidate_pairs(
            account_id, date_window_days=SCAN_DATE_WINDOW_DAYS
        )
        created = 0

        for txn_a, payee_a, txn_b, payee_b in pairs:
            date_delta = abs((txn_a.date - txn_b.date).days)
            date_score = 1.0 - (date_delta / (SCAN_DATE_WINDOW_DAYS + 1))
            payee_score = _payee_similarity(payee_a or "", payee_b or "")
            score = round(date_score * 0.65 + payee_score * 0.35, 4)

            if score < SCAN_REVIEW_THRESHOLD:
                continue
            if await self.match_repo.exists_for_pair(txn_a.id, txn_b.id):
                continue

            # Treat the newer transaction as "synced" (the potential duplicate)
            synced, manual = (txn_a, txn_b) if txn_a.date >= txn_b.date else (txn_b, txn_a)
            await self.match_repo.create(
                synced_transaction_id=synced.id,
                manual_transaction_id=manual.id,
                confidence_score=score,
            )
            created += 1

        return created
