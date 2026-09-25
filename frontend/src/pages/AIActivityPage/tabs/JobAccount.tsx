import { useMemo } from 'react'
import { Wallet } from 'lucide-react'
import { useAccounts } from '../../../api/accounts'
import type { AIJob } from '../../../api/aiJobs'
import type { ComboboxOption } from '../../../components/common/Combobox/Combobox'
import { useAccountMove } from '../../../hooks/useAccountMove'
import { accountNameMap, openAccounts } from '../../../utils/accountLists'
import { JobField } from './JobField'

/**
 * Which account this job's transaction is in — named on every row, and
 * changeable on the ones still waiting for approval.
 *
 * The review list used to name the payee and the amount and say nothing at
 * all about the account, so a receipt scanned against the wrong card was
 * approved looking correct and only surfaced later, as a balance that did
 * not match. The account is the one field on an AI draft that no model
 * chose: it is whatever was selected before the photo.
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

  // Only a row that exists can be moved, and only one still waiting for the
  // user is worth moving from here — an approved row is edited in its
  // register like any other.
  const txnId = job.transaction_id
  const here = job.transaction_account_id
  const movable = !!txnId && !!here && job.needs_review

  return (
    <JobField
      icon={<Wallet size={11} aria-hidden />}
      name={names.get(currentId) ?? 'Unknown account'}
      title="The account this transaction is in"
      editTitle="Change the account this transaction is in"
      editable={movable}
      value={here}
      options={options}
      placeholder="Move to account…"
      pickerLabel="Move to account"
      onPick={(id) => {
        if (txnId && here) commitMove({ id: txnId, account_id: here }, id)
      }}
    />
  )
}
