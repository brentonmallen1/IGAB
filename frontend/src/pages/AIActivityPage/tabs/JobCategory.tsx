import { useMemo } from 'react'
import toast from 'react-hot-toast'
import { Split, Tag } from 'lucide-react'
import type { AIJob } from '../../../api/aiJobs'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { apiErrorMessage } from '../../../api/client'
import { useUpdateTransaction } from '../../../api/transactions'
import { aiSuggestedCategory } from '../../../components/ai/draftNotes'
import { filingCategoryOptions } from '../../../utils/categoryPickers'
import { JobField } from './JobField'

/**
 * Which category this job's transaction is filed in, and what the model
 * picked when the row is filed somewhere else. Changeable while the row
 * waits for approval, like the account beside it.
 *
 * The row used to show the model's reason and nothing about where the row
 * was filed, so an uncategorized row read the same as one filed where the
 * reason said. The filed category is served (`transaction_category_id`),
 * because the client holds a transaction id and nothing else about the row.
 * The name comes from the category list this picker needs anyway. The
 * model's pick is `result.draft.category`, which nothing here writes to.
 *
 * Picking PATCHes the transaction, the same call the register makes: it goes
 * on the undo stack, and it does not approve the row.
 */
export function JobCategory({ job, budgetId }: { job: AIJob; budgetId: string }) {
  // Archived included, so a row filed in an envelope archived since is still
  // named. Only what a row may be filed to is offered.
  const { data: categories = [] } = useCategories(budgetId, true)
  const { data: groups = [] } = useCategoryGroups(budgetId, true)
  const update = useUpdateTransaction(budgetId)

  const options = useMemo(() => filingCategoryOptions(categories, groups), [categories, groups])
  const groupNames = useMemo(() => new Map(groups.map((g) => [g.id, g.name])), [groups])

  // Nothing is filed without a row: a queued scan, one waiting for an
  // account, one whose row was deleted. The served account is null exactly
  // then, from the same subquery.
  const txnId = job.transaction_id
  if (!txnId || !job.transaction_account_id) return null

  // A split's category is its lines'. The server refuses one on the parent,
  // so there is nothing to pick here; the row's Edit/View opens the lines.
  if (job.transaction_is_split) {
    return (
      <span
        className="ai-activity__field"
        title="Split across categories. Open the transaction to see its lines."
      >
        <Split size={11} aria-hidden />
        Split
      </span>
    )
  }

  const filedId = job.transaction_category_id
  const filed = filedId ? categories.find((c) => c.id === filedId) : undefined
  // Until the list arrives, a filed row cannot be compared with the pick.
  const suggested =
    filedId && !filed
      ? null
      : aiSuggestedCategory(
          job.result?.draft,
          filed
            ? { name: filed.name, group: groupNames.get(filed.category_group_id) ?? null }
            : null
        )

  return (
    <>
      <JobField
        icon={<Tag size={11} aria-hidden />}
        name={filedId ? (filed?.name ?? 'Unknown category') : 'Uncategorized'}
        title="The category this transaction is filed in"
        editTitle="Change the category this transaction is filed in"
        editable={job.needs_review}
        value={filedId}
        options={options}
        placeholder="File in category…"
        pickerLabel="File in category"
        onPick={(id) =>
          update.mutate(
            { id: txnId, category_id: id },
            {
              onError: (err) => toast.error(apiErrorMessage(err, 'Could not change the category')),
            }
          )
        }
      />
      {suggested && (
        <span className="ai-activity__suggested" title="The category the model picked">
          AI suggested {suggested}
        </span>
      )}
    </>
  )
}
