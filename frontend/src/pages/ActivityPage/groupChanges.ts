import type { Change } from '../../api/changes'

/**
 * Group consecutive changes that share a real batch_id, for the "Batch of N"
 * header. A null batch_id means "not part of any batch" and always stands
 * alone — grouping nulls together labeled two independent receipt failures
 * "Batch of 2" (null !== null is false, so the naive comparison merged them).
 *
 * Own module (not exported from the page) so the page keeps fast refresh.
 */
export function groupChanges(
  changes: Change[]
): Array<{ batchId: string | null; changes: Change[] }> {
  const grouped: Array<{ batchId: string | null; changes: Change[] }> = []
  for (const change of changes) {
    const last = grouped[grouped.length - 1]
    if (change.batch_id !== null && last && last.batchId === change.batch_id) {
      last.changes.push(change)
    } else {
      grouped.push({ batchId: change.batch_id, changes: [change] })
    }
  }
  return grouped
}
