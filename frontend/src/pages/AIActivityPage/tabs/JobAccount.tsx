import { useMemo, useState } from 'react'
import { Wallet } from 'lucide-react'
import { useAccounts } from '../../../api/accounts'
import type { AIJob } from '../../../api/aiJobs'
import { Combobox, type ComboboxOption } from '../../../components/common/Combobox/Combobox'
import { useAccountMove } from '../../../hooks/useAccountMove'
import { accountNameMap, openAccounts } from '../../../utils/accountLists'

/**
 * Which account this job's transaction is in — named on every row, and
 * changeable on the ones still waiting for approval.
 *
 * The review list used to name the payee, the amount and the category and
 * say nothing at all about the account, so a receipt scanned against the
 * wrong card was approved looking correct and only surfaced later, as a
 * balance that did not match. The account is the one field on an AI draft
 * that no model chose: it is whatever was selected before the photo.
 *
 * `transaction_account_id` is served (see the model's comment) because the
 * client holds a transaction id and nothing else about the row. The
 * payload's account is the fallback for a job whose transaction does not
 * exist yet — a queued scan, where it is a statement of where the row WILL
 * go rather than where it is.
 */
export function JobAccount({ job, budgetId }: { job: AIJob; budgetId: string }) {
  const { data: accounts = [] } = useAccounts(budgetId)
  const commitMove = useAccountMove(budgetId)
  const [picking, setPicking] = useState(false)

  // The unfiltered list names the row; only open accounts are offered as
  // destinations (utils/accountLists).
  const names = useMemo(() => accountNameMap(accounts), [accounts])
  const options = useMemo<ComboboxOption[]>(
    () =>
      openAccounts(accounts).map((a) => ({
        id: a.id,
        label: a.name,
        group: a.on_budget ? '' : 'Tracking',
      })),
    [accounts]
  )

  const currentId = job.transaction_account_id ?? job.payload.account_id ?? null
  if (!currentId) return null
  const name = names.get(currentId) ?? 'Unknown account'

  // Only a row that exists can be moved, and only one still waiting for the
  // user is worth moving from here — an approved row is edited in its
  // register like any other.
  const movable = !!job.transaction_id && !!job.transaction_account_id && job.needs_review

  if (picking && job.transaction_id && job.transaction_account_id) {
    return (
      <span className="ai-activity__account ai-activity__account--picking">
        <Combobox
          value={job.transaction_account_id}
          options={options}
          onChange={(id) => {
            commitMove({ id: job.transaction_id!, account_id: job.transaction_account_id! }, id)
            setPicking(false)
          }}
          placeholder="Move to account…"
          aria-label="Move to account"
          autoFocus
          onBlurClose={() => setPicking(false)}
        />
      </span>
    )
  }

  if (!movable) {
    return (
      <span className="ai-activity__account" title="The account this transaction is in">
        <Wallet size={11} aria-hidden />
        {name}
      </span>
    )
  }

  return (
    <button
      className="ai-activity__account ai-activity__account--button"
      onClick={() => setPicking(true)}
      title="Change the account this transaction is in"
    >
      <Wallet size={11} aria-hidden />
      {name}
    </button>
  )
}
