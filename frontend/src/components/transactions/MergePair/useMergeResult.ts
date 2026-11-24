import { apiErrorMessage } from '../../../api/client'
import { useMergePreview } from '../../../api/transactions'
import type { MergeKeep, MergePreview } from '../../../types'

export interface MergeResult {
  /** The server's answer for the current picks; undefined while it is asked
   *  and when the merge would be refused. */
  preview: MergePreview | undefined
  /** Why the server would refuse this merge, when it would. */
  refusal: string | null
  /** There is a result to merge into: the only state a dialog may offer its
   *  Merge / Accept button in. */
  ready: boolean
}

/**
 * What `MergePair` draws and what its dialog's button waits on, from the one
 * preview query. The register's merge dialog and the duplicate review each
 * read the query themselves — the same three expressions and the same
 * fallback sentence, twice.
 */
export function useMergeResult(
  budgetId: string | null,
  transactionIds: readonly [string, string] | null,
  keep: MergeKeep
): MergeResult {
  const query = useMergePreview(budgetId, transactionIds, keep)
  if (query.isError) {
    return {
      preview: undefined,
      refusal: apiErrorMessage(query.error, 'the result could not be worked out'),
      ready: false,
    }
  }
  return { preview: query.data, refusal: null, ready: !!query.data }
}
