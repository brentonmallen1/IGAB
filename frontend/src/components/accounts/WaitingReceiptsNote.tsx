import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAIJobs, usePlaceReceipt, type AIJob } from '../../api/aiJobs'
import { apiErrorMessage } from '../../api/client'
import { useFormatters } from '../../hooks/useFormatters'
import { parseApiDecimal } from '../../utils/money'
import './WaitingReceiptsNote.css'

/** How many waiting receipts the reconcile question lists by name. */
const SHOWN = 3

/**
 * Scanned receipts with no account, said before a reconcile begins.
 *
 * A receipt waiting for an account moves no money, so a purchase paid from
 * this account can be missing from the balance about to be checked — the
 * one moment that gap costs something. Listed with a one-tap "It's from
 * here"; the ones whose card is on file for this account come first.
 */
export function WaitingReceiptsNote({
  budgetId,
  accountId,
  accountName,
}: {
  budgetId: string
  accountId: string
  accountName: string
}) {
  const { data } = useAIJobs(budgetId, { status: 'unplaced', limit: 200 })
  const place = usePlaceReceipt(budgetId)
  const { formatMoney, formatDayMonth } = useFormatters()
  const jobs = [...(data?.jobs ?? [])].sort(
    (a, b) =>
      Number(b.card_ending_account_id === accountId) -
      Number(a.card_ending_account_id === accountId)
  )
  if (jobs.length === 0) return null

  const label = (job: AIJob) => {
    const draft = job.result?.draft
    const parts = [
      draft?.payee ?? 'Receipt',
      draft?.amount ? formatMoney(parseApiDecimal(draft.amount)) : null,
      draft?.date ? formatDayMonth(draft.date) : null,
    ]
    return parts.filter(Boolean).join(' · ')
  }

  return (
    <div className="waiting-receipts" role="note">
      <p className="waiting-receipts__lede">
        {jobs.length === 1
          ? '1 scanned receipt isn’t in any account yet.'
          : `${jobs.length} scanned receipts aren’t in any account yet.`}{' '}
        If one was paid from {accountName}, this balance doesn’t include it.
      </p>
      <ul className="waiting-receipts__list">
        {jobs.slice(0, SHOWN).map((job) => {
          // The bank's own row for it is already in this account: the
          // receipt goes on that row, never beside it as a duplicate.
          const row = job.bank_match?.account_id === accountId ? job.bank_match : null
          return (
            <li key={job.id} className="waiting-receipts__row">
              <span className="waiting-receipts__what">{label(job)}</span>
              <button
                type="button"
                className="waiting-receipts__place"
                disabled={place.isPending}
                onClick={() =>
                  place.mutate(
                    row
                      ? { jobId: job.id, transaction_id: row.id }
                      : { jobId: job.id, account_id: accountId },
                    {
                      onSuccess: () => toast.success(`Receipt put in ${accountName}`),
                      onError: (err) =>
                        toast.error(apiErrorMessage(err, 'Could not place the receipt')),
                    }
                  )
                }
              >
                {row ? `It’s the ${formatDayMonth(row.date)} charge` : 'It’s from here'}
              </button>
            </li>
          )
        })}
      </ul>
      {jobs.length > SHOWN && (
        <Link to="/ai-activity" className="waiting-receipts__more">
          {jobs.length - SHOWN} more in AI Activity
        </Link>
      )}
    </div>
  )
}
