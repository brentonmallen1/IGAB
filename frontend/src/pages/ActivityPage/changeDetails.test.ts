import { describe, expect, it } from 'vitest'
import type { Change } from '../../api/changes'
import { diffRows, fieldLabel, formatFieldValue, summarizeChange, truncate } from './changeDetails'

const PAYEE = '11111111-1111-1111-1111-111111111111'
const ACCOUNT = '22222222-2222-2222-2222-222222222222'
const CATEGORY = '33333333-3333-3333-3333-333333333333'
const TAG_A = '44444444-4444-4444-4444-444444444444'
const TAG_B = '55555555-5555-5555-5555-555555555555'

const names = {
  [PAYEE]: 'Harborstone Market',
  [ACCOUNT]: 'Everyday Checking',
  [CATEGORY]: 'Groceries',
  [TAG_A]: 'Essential',
  [TAG_B]: 'Splurge',
}

function change(over: Partial<Change>): Change {
  return {
    id: 'c1',
    seq: 1,
    undo_seq: null,
    entity_type: 'transaction',
    entity_id: 'e1',
    action: 'create',
    before: null,
    after: null,
    batch_id: null,
    source: 'manual',
    undone_at: null,
    created_at: '2026-09-05T10:00:00+00:00',
    user_id: null,
    user_display_name: null,
    ...over,
  }
}

describe('summarizeChange', () => {
  it('names the payee and account on a transaction, not their ids', () => {
    const summary = summarizeChange(
      change({ after: { amount: '-42.50', payee_id: PAYEE, account_id: ACCOUNT } }),
      names
    )
    expect(summary).toBe('-$42.50 · Harborstone Market · Everyday Checking')
  })

  it('keeps the context on a delete, read from the before side', () => {
    const summary = summarizeChange(
      change({
        action: 'delete',
        before: { amount: '-42.50', payee_id: PAYEE, account_id: ACCOUNT },
      }),
      names
    )
    expect(summary).toBe('-$42.50 · Harborstone Market · Everyday Checking')
  })

  it('truncates a long payee instead of flooding the line', () => {
    const longNames = { [PAYEE]: 'The Extremely Long Payee Name Emporium & Co' }
    const summary = summarizeChange(
      change({ after: { amount: '-5.00', payee_id: PAYEE } }),
      longNames
    )
    expect(summary).toBe('-$5.00 · The Extremely Long Paye…')
  })

  it('leaves the line bare when the names map has no answer', () => {
    const summary = summarizeChange(
      change({ after: { amount: '-5.00', payee_id: PAYEE, account_id: ACCOUNT } }),
      {}
    )
    expect(summary).toBe('-$5.00')
  })

  it('names the category on an assignment', () => {
    const summary = summarizeChange(
      change({
        entity_type: 'assignment',
        action: 'update',
        before: { assigned: '0', category_id: CATEGORY },
        after: { assigned: '120', category_id: CATEGORY },
      }),
      names
    )
    expect(summary).toBe('Assigned → $120.00 · Groceries')
  })

  it('names tags in a membership move', () => {
    const summary = summarizeChange(
      change({
        entity_type: 'category_tags',
        action: 'update',
        before: { _tag_ids: [TAG_A] },
        after: { _tag_ids: [TAG_B] },
      }),
      names
    )
    expect(summary).toBe('Tags → Splurge')
  })
})

describe('diffRows', () => {
  it('shows only the fields an update moved, before → after', () => {
    const rows = diffRows(
      change({
        action: 'update',
        before: { amount: '-42.50', memo: 'weekly shop', payee_id: PAYEE },
        after: { amount: '-60.00', memo: 'weekly shop', payee_id: PAYEE },
      }),
      names
    )
    expect(rows).toEqual([{ label: 'amount', before: '-$42.50', after: '-$60.00' }])
  })

  it('resolves reference moves to names on both sides', () => {
    const other = { ...names, [TAG_A]: 'Essential' }
    const rows = diffRows(
      change({
        entity_type: 'category_tags',
        action: 'update',
        before: { _tag_ids: [TAG_A] },
        after: { _tag_ids: [TAG_A, TAG_B] },
      }),
      other
    )
    expect(rows).toEqual([{ label: 'tags', before: 'Essential', after: 'Essential, Splurge' }])
  })

  it('shows a create on the after side only, skipping empty fields', () => {
    const rows = diffRows(
      change({ after: { amount: '-42.50', memo: null, account_id: ACCOUNT } }),
      names
    )
    expect(rows).toEqual([
      { label: 'amount', before: null, after: '-$42.50' },
      { label: 'account', before: null, after: 'Everyday Checking' },
    ])
  })

  it('shows a delete on the before side only', () => {
    const rows = diffRows(
      change({ action: 'delete', before: { name: 'Kayak', cost: '450' } }),
      names
    )
    expect(rows).toEqual([
      { label: 'name', before: 'Kayak', after: null },
      { label: 'cost', before: '$450.00', after: null },
    ])
  })

  it('returns nothing for reorders and archives — their payloads are bookkeeping', () => {
    expect(diffRows(change({ action: 'reorder', before: { _order: ['a'] } }), names)).toEqual([])
    expect(
      diffRows(change({ action: 'archive', after: { x: { is_archived: true } } }), names)
    ).toEqual([])
  })
})

describe('formatFieldValue', () => {
  it('stubs an id the names map does not know instead of printing a UUID', () => {
    expect(formatFieldValue('payee_id', PAYEE, {})).toBe('#1111')
  })
  it('renders booleans, blanks and documents readably', () => {
    expect(formatFieldValue('auto_create', true, {})).toBe('yes')
    expect(formatFieldValue('memo', null, {})).toBe('—')
    expect(formatFieldValue('payload', { a: 1 }, {})).toBe('(document)')
    expect(formatFieldValue('interest_rate', '6.5', {})).toBe('6.5%')
  })
})

describe('labels and truncation', () => {
  it('speaks field names like a person', () => {
    expect(fieldLabel('category_id')).toBe('category')
    expect(fieldLabel('_tag_ids')).toBe('tags')
    expect(fieldLabel('next_occurrence_date')).toBe('next occurrence date')
  })
  it('truncate keeps short strings whole', () => {
    expect(truncate('Checking')).toBe('Checking')
  })
})
