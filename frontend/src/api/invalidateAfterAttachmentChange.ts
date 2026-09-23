import type { QueryClient } from '@tanstack/react-query'
import { ROOT } from './queryKeys'

/**
 * Every cache that answers "does this transaction have a receipt?".
 *
 * Two caches, not one, and that is the point: the editor's panel is keyed per
 * transaction (`useAttachments`), while the register's indicator is one bulk
 * map over the whole visible id list (`useCheckAttachments`). A receipt that
 * moves between rows changes both, and a caller that refreshes only the panel
 * leaves the register saying the row has no image while the panel shows it.
 *
 * That is exactly the bug this consolidates. The pair was spelled four times —
 * upload, delete, the row's own file input, and undo — and the one place that
 * needed it most did not spell it at all: `invalidateAfterTransactionChange`,
 * which is what a merge runs. So merging a plain row with one holding a
 * receipt moved the receipt to the survivor, and the register kept serving
 * the cached `false` it had for that id. Undo refreshed it; the merge that
 * caused it did not.
 *
 * The bulk map can only be invalidated at its root: its key carries the
 * register's entire id list, so there is no per-transaction entry to target.
 *
 * @param transactionIds the rows whose receipt set changed. Omit when the
 *   caller cannot know — undo restores whatever a batch touched — and every
 *   per-transaction panel is refreshed instead.
 */
export function invalidateAfterAttachmentChange(
  qc: QueryClient,
  transactionIds?: string[]
): Promise<void> {
  const keys: unknown[][] =
    transactionIds && transactionIds.length > 0
      ? transactionIds.map((id) => [ROOT.attachments, id])
      : [[ROOT.attachments]]
  keys.push([ROOT.attachmentCheck])
  return Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey }))).then(
    () => undefined
  )
}
