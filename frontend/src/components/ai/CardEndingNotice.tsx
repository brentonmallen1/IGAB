import { CreditCard } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../api/accounts'
import type { AIJob } from '../../api/aiJobs'
import { useCreateCardEnding } from '../../api/cardEndings'
import { apiErrorMessage } from '../../api/client'
import { useAccountMove } from '../../hooks/useAccountMove'
import { accountNameMap } from '../../utils/accountLists'
import { cardEndingNote } from './draftNotes'
import './CardEndingNotice.css'

/**
 * The card that paid, beside a scan still waiting for review: "this is
 * another account's card" with a move, or "remember this card" for an
 * ending nobody has on file. Silent when the card is this account's own.
 *
 * `canMove` is off inside the transaction editor, which has its own Account
 * field and its own unsaved state — a move committed from under it would be
 * overwritten by the editor's save.
 */
export function CardEndingNotice({
  job,
  budgetId,
  canMove,
}: {
  job: AIJob
  budgetId: string
  canMove: boolean
}) {
  const { data: accounts = [] } = useAccounts(budgetId)
  const remember = useCreateCardEnding(budgetId)
  const move = useAccountMove(budgetId)
  const note = cardEndingNote(job)
  if (!note || !job.needs_review) return null
  const names = accountNameMap(accounts)
  const here = names.get(note.hereId) ?? 'this account'

  if (note.kind === 'elsewhere') {
    const owner = names.get(note.ownerId) ?? 'another account'
    return (
      <div className="card-ending-notice card-ending-notice--elsewhere" role="status">
        <CreditCard size={13} aria-hidden />
        <span>
          Paid with the card ending {note.last4}, which is on {owner}, not {here}.
        </span>
        {canMove && job.transaction_id && (
          <button
            type="button"
            className="card-ending-notice__action"
            onClick={() => move({ id: job.transaction_id!, account_id: note.hereId }, note.ownerId)}
          >
            Move to {owner}
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="card-ending-notice" role="status">
      <CreditCard size={13} aria-hidden />
      <span>Paid with a card ending {note.last4}.</span>
      <button
        type="button"
        className="card-ending-notice__action"
        disabled={remember.isPending}
        onClick={() =>
          remember.mutate(
            { account_id: note.hereId, last4: note.last4 },
            {
              onSuccess: () => toast.success(`Card ending ${note.last4} remembered for ${here}`),
              onError: (err) => toast.error(apiErrorMessage(err, 'Could not remember that card')),
            }
          )
        }
      >
        Remember it for {here}
      </button>
    </div>
  )
}
