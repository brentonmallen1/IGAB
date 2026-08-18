/**
 * Batch grouping for the Activity page. The regression: rows with a null
 * batch_id merged with their null-batch neighbors (null !== null is false),
 * so two independent receipt failures rendered as "Batch of 2".
 */
import { describe, expect, it } from 'vitest'
import { groupChanges } from './groupChanges'
import type { Change } from '../../api/changes'

function change(id: string, batchId: string | null): Change {
  return {
    id,
    entity_type: 'transaction',
    entity_id: `entity-${id}`,
    action: 'create',
    before: null,
    after: null,
    batch_id: batchId,
    source: 'ai',
    undone_at: null,
    created_at: '2026-08-17T13:53:41+00:00',
  }
}

describe('groupChanges', () => {
  it('never groups consecutive null-batch rows', () => {
    const grouped = groupChanges([change('a', null), change('b', null)])
    expect(grouped).toHaveLength(2)
    expect(grouped.every((g) => g.changes.length === 1)).toBe(true)
  })

  it('groups consecutive rows sharing a real batch_id', () => {
    const grouped = groupChanges([change('a', 'batch-1'), change('b', 'batch-1')])
    expect(grouped).toHaveLength(1)
    expect(grouped[0].changes.map((c) => c.id)).toEqual(['a', 'b'])
  })

  it('splits on batch boundaries and keeps nulls standalone in interleavings', () => {
    const grouped = groupChanges([
      change('a', 'batch-1'),
      change('b', 'batch-1'),
      change('c', null),
      change('d', null),
      change('e', 'batch-2'),
    ])
    expect(grouped.map((g) => ({ batch: g.batchId, n: g.changes.length }))).toEqual([
      { batch: 'batch-1', n: 2 },
      { batch: null, n: 1 },
      { batch: null, n: 1 },
      { batch: 'batch-2', n: 1 },
    ])
  })

  it('does not merge same batch_id across a null gap', () => {
    // Non-consecutive rows of one batch stay visually separate — the list is
    // chronological and a gap means something else happened in between.
    const grouped = groupChanges([
      change('a', 'batch-1'),
      change('b', null),
      change('c', 'batch-1'),
    ])
    expect(grouped).toHaveLength(3)
  })

  it('handles the empty list', () => {
    expect(groupChanges([])).toEqual([])
  })
})
