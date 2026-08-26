"""Transaction matching service.

Finds manually entered transactions that likely correspond to newly synced
transactions and creates a link between them.  When confidence is high
enough the link is auto-accepted; otherwise it is stored as "pending" for
human review. Accepting is a merge — TransactionService.merge, the one
merge — so the review queue and the user's explicit merge cannot drift.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from igab.db.models import Transaction
from igab.domain.exceptions import InvariantViolation
from igab.domain.matching import date_proximity, payee_similarity
from igab.repositories.payee_repo import PayeeRepository
from igab.repositories.transaction_match_repo import TransactionMatchRepository
from igab.repositories.transaction_repo import TransactionRepository

if TYPE_CHECKING:
    from igab.services.transaction_service import TransactionService

AUTO_ACCEPT_THRESHOLD = 0.90
DATE_WINDOW_DAYS = 5


SCAN_REVIEW_THRESHOLD = 0.55
SCAN_DATE_WINDOW_DAYS = 5


#: What a missing payee counts for here. Zero rather than neutral: this scores
#: a synced row against something the user typed, and a manual entry with no
#: payee is not evidence of anything. Safe because 0.4 (amount) + 0.3 (date)
#: = 0.7, below the 0.90 auto threshold. Pinned in test_matching_scores.py.
_UNKNOWN_PAYEE_SCORE = 0.0


def _payee_similarity(a: str, b: str) -> float:
    return payee_similarity(a, b, unknown=_UNKNOWN_PAYEE_SCORE)


def _date_score(synced: date, manual: date) -> float:
    """1.0 for same day, decays linearly to 0 at DATE_WINDOW_DAYS+1."""
    return date_proximity(synced, manual, window_days=DATE_WINDOW_DAYS)


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
        txn_service: "TransactionService",
    ) -> None:
        self.session = session
        self.txn_repo = txn_repo
        self.match_repo = match_repo
        self.payee_repo = payee_repo
        self.txn_service = txn_service

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

        # The match row is written AFTER the outcome is known: an accepted row
        # with no merge behind it (the merge refused) is a lie the review
        # queue would never show. Candidates share the exact amount, so the
        # merge's amount rule cannot be what refuses.
        status = "pending"
        if best_score >= AUTO_ACCEPT_THRESHOLD:
            try:
                await self._accept_link(synced_txn, best_candidate, best_score)
                status = "accepted"
            except InvariantViolation:
                status = "pending"

        await self.match_repo.create(
            synced_transaction_id=synced_txn.id,
            manual_transaction_id=best_candidate.id,
            confidence_score=best_score,
            status=status,
        )

    async def _accept_link(
        self,
        synced_txn: Transaction,
        manual_txn: Transaction,
        confidence: float,
    ) -> None:
        """Merge the pair down to one row — TransactionService.merge is the one
        merge; who survives and what the bank row contributes are decided
        there (domain.merging, domain.bank_posting)."""
        if synced_txn.id == manual_txn.id:
            return  # a transaction can never be its own duplicate
        if synced_txn.is_deleted or manual_txn.is_deleted:
            return  # stale match — one side is already gone
        await self.txn_service.merge(synced_txn.budget_id, [synced_txn.id, manual_txn.id])

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


def build_transaction_matching_service(
    session: AsyncSession, txn_service: "TransactionService"
) -> TransactionMatchingService:
    """The matching service over one session, sharing the caller's
    TransactionService so every accept goes through the same merge (and the
    same change-log actor)."""
    return TransactionMatchingService(
        session,
        TransactionRepository(session),
        TransactionMatchRepository(session),
        PayeeRepository(session),
        txn_service,
    )
