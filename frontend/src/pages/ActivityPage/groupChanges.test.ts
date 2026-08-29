/**
 * Batch grouping for the Activity page. The regression: rows with a null
 * batch_id merged with their null-batch neighbors (null !== null is false),
 * so two independent receipt failures rendered as "Batch of 2".
 */
import { describe, expect, it } from 'vitest'
import { groupChanges, summarizeBatch } from './groupChanges'
import type { Change } from '../../api/changes'

function change(id: string, batchId: string | null, over: Partial<Change> = {}): Change {
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
    user_id: null,
    user_display_name: null,
    ...over,
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

describe('summarizeBatch', () => {
  it('names the action and the count when a batch does one thing', () => {
    expect(
      summarizeBatch([
        change('a', 'b1', { action: 'update', entity_type: 'assignment' }),
        change('b', 'b1', { action: 'update', entity_type: 'assignment' }),
        change('c', 'b1', { action: 'update', entity_type: 'assignment' }),
      ])
    ).toBe('Updated 3 assignments')
  })

  it('keeps a singular label singular', () => {
    expect(summarizeBatch([change('a', 'b1', { action: 'delete' })])).toBe('Deleted 1 transaction')
  })

  it('does not pluralize a label that already is', () => {
    // entityTypeLabel('budget') is "category groups" — the only entity whose
    // label arrives plural, and "category groupss" is how that gets noticed.
    expect(
      summarizeBatch([
        change('a', 'b1', { action: 'reorder', entity_type: 'budget' }),
        change('b', 'b1', { action: 'reorder', entity_type: 'budget' }),
      ])
    ).toBe('Reordered 2 category groups')
  })

  it('falls back to a count when a batch does more than one kind of thing', () => {
    // A merge writes a delete and an update; naming either one would lie.
    expect(
      summarizeBatch([
        change('a', 'b1', { action: 'delete', entity_type: 'payee' }),
        change('b', 'b1', { action: 'update', entity_type: 'payee' }),
      ])
    ).toBe('2 changes in one action')
  })

  it('says nothing about an empty batch', () => {
    expect(summarizeBatch([])).toBe('')
  })
})
