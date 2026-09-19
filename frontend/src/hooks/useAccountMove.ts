import toast from 'react-hot-toast'
import { apiErrorMessage } from '../api/client'
import { useUpdateTransaction } from '../api/transactions'

/**
 * Commit a transaction's move to another account.
 *
 * Two surfaces offer the move in place — the all-accounts register's Account
 * cell and the AI review list — and both need the same two non-obvious
 * things, which is why this is one function rather than two:
 *
 * - **A no-op pick writes nothing.** The server drops an unchanged
 *   `account_id` anyway, but the change-log row it would record sits in
 *   ⌘Z's way, so the next undo takes back something the user never did.
 * - **A refusal is said out loud.** This is the one inline commit a user
 *   can reach by accident — a categorized row into a tracking account, a
 *   transfer leg into its own partner's account. Silence reads as "it
 *   didn't take"; the server's sentence says which it was.
 *
 * Whether a row may move at all is `TransactionEditor/accountMove.ts`, and
 * the server's own rule (`domain/account_move.py`) refuses regardless of
 * what any client offers.
 */
export function useAccountMove(budgetId: string) {
  const updateTxn = useUpdateTransaction(budgetId)

  return function move(transaction: { id: string; account_id: string }, targetId: string | null) {
    if (!targetId || targetId === transaction.account_id) return
    updateTxn.mutate(
      { id: transaction.id, account_id: targetId },
      {
        onError: (err) => toast.error(apiErrorMessage(err, 'Could not move this transaction')),
      }
    )
  }
}
