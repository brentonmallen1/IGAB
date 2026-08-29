import type { Change } from '../../api/changes'
import { actionTypeLabel, entityTypeLabel } from './changeLabels'

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

/**
 * One line for a whole batch, so a bulk assign of forty categories is one
 * entry in the list rather than forty.
 *
 * A batch is one compound operation, so its rows almost always share an
 * action and an entity type — "Assigned 41 categories". Where they don't
 * (a merge writes a delete and an update; an import can touch several kinds)
 * the count alone is the honest summary.
 */
export function summarizeBatch(changes: Change[]): string {
  if (changes.length === 0) return ''
  const actions = new Set(changes.map((c) => c.action))
  const entities = new Set(changes.map((c) => c.entity_type))
  const n = changes.length
  if (actions.size === 1 && entities.size === 1) {
    const entity = entityTypeLabel(changes[0].entity_type)
    // entityTypeLabel returns 'category groups' already plural for the one
    // case where the entity is the budget itself.
    const plural = n === 1 || entity.endsWith('s') ? entity : `${entity}s`
    return `${actionTypeLabel(changes[0].action)} ${n} ${plural}`
  }
  return `${n} changes in one action`
}
