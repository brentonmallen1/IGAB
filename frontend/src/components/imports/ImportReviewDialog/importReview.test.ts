import { describe, it, expect } from 'vitest'
import {
  buildRows,
  filterRows,
  initialFilter,
  pendingUpdates,
  repairableTransferLegs,
  stepsFor,
  toggleTag,
  type Draft,
  type ReviewCategory,
} from './importReview'
import type { YnabImportResult } from '../../../api/imports'

const SAVINGS = 'tag-savings'
const SUBSCRIPTION = 'tag-subscription'
const TRAVEL = 'tag-travel' // the user's own, no system key
const KEY_BY_ID = { [SAVINGS]: 'savings', [SUBSCRIPTION]: 'subscription' }

function category(over: Partial<ReviewCategory> = {}): ReviewCategory {
  return {
    id: 'c1',
    name: 'Amazon Prime',
    groupName: 'Long Term Expenses',
    hidden: false,
    tagIds: [],
    ...over,
  }
}

function summary(over: Partial<YnabImportResult> = {}): YnabImportResult {
  return {
    accounts: 3,
    category_groups: 4,
    categories: 20,
    transactions: 400,
    skipped: 0,
    assignments: 50,
    accounts_skipped: 0,
    accounts_closed: 0,
    transactions_excluded: 0,
    transfer_legs_unpaired: 0,
    transfer_legs_in_splits: 0,
    categories_tagged: 0,
    tagged_categories: [],
    credit_card_payment_assignments_skipped: 0,
    credit_card_payment_reserves_skipped: '0',
    parity: null,
    errors: [],
    ...over,
  }
}

describe('stepsFor', () => {
  it('offers the report only when there is one', () => {
    expect(stepsFor(summary())).toEqual(['summary', 'tags', 'accounts'])
  })

  it('goes straight to what can still be changed without one', () => {
    // A budget made by hand, or imported before this was recorded — the case
    // the review is most useful for, since those have no tags at all.
    expect(stepsFor(null)).toEqual(['tags', 'accounts'])
    expect(stepsFor(undefined)).toEqual(['tags', 'accounts'])
  })
})

describe('buildRows', () => {
  it('reads held keys through the tag map, ignoring the user’s own tags', () => {
    const cat = category({ tagIds: [SAVINGS, TRAVEL] })
    const [row] = buildRows([cat], [], [], KEY_BY_ID, {})
    expect(row.held).toEqual(['savings'])
  })

  it('marks the rows this import decided, and says what matched', () => {
    const cat = category()
    const [row] = buildRows(
      [cat],
      [],
      [{ category_id: 'c1', system_key: 'savings', matched_on: 'Emergency Fund' }],
      KEY_BY_ID,
      {}
    )
    expect(row.importTagged).toBe(true)
    expect(row.importMatchedOn).toBe('Emergency Fund')
  })

  it('drops a suggestion once the draft has accepted it', () => {
    // Otherwise an accepted proposal stays in the list and reads as though it
    // had not applied.
    const cat = category()
    const suggestions = [
      { category_id: 'c1', system_key: 'subscription', matched_on: 'Amazon Prime', applied_on_import: false },
    ]
    const before = buildRows([cat], suggestions, [], KEY_BY_ID, {})
    expect(before[0].suggestions).toHaveLength(1)

    const draft: Draft = { c1: [SUBSCRIPTION] }
    const after = buildRows([cat], suggestions, [], KEY_BY_ID, draft)
    expect(after[0].suggestions).toEqual([])
    expect(after[0].held).toEqual(['subscription'])
  })
})

describe('filterRows', () => {
  const decided = category({ id: 'decided' })
  const proposed = category({ id: 'proposed' })
  const untouched = category({ id: 'untouched' })
  const rows = buildRows(
    [decided, proposed, untouched],
    [
      { category_id: 'proposed', system_key: 'essential', matched_on: 'Rent', applied_on_import: false },
    ],
    [{ category_id: 'decided', system_key: 'savings', matched_on: 'Savings' }],
    KEY_BY_ID,
    {}
  )

  it('opens on what the import decided', () => {
    expect(filterRows(rows, 'decided', {}).map((r) => r.category.id)).toEqual(['decided'])
  })

  it('keeps a row the user is working on, even once it no longer qualifies', () => {
    const ids = filterRows(rows, 'decided', { untouched: [SAVINGS] }).map((r) => r.category.id)
    expect(ids).toEqual(['decided', 'untouched'])
  })

  it('reaches the ones only proposed, and all of them', () => {
    expect(filterRows(rows, 'suggested', {}).map((r) => r.category.id)).toEqual(['proposed'])
    expect(filterRows(rows, 'all', {})).toHaveLength(3)
  })
})

describe('toggleTag', () => {
  it('seeds from what the category carries, so other tags survive', () => {
    // The server replaces rather than merges: a draft holding only the system
    // tag being changed would drop the user's own.
    const cat = category({ tagIds: [TRAVEL] })
    expect(toggleTag({}, cat, SUBSCRIPTION)).toEqual({ c1: [TRAVEL, SUBSCRIPTION] })
  })

  it('removes one that is already there', () => {
    const cat = category({ tagIds: [SAVINGS, TRAVEL] })
    expect(toggleTag({}, cat, SAVINGS)).toEqual({ c1: [TRAVEL] })
  })
})

describe('pendingUpdates', () => {
  const cat = category({ tagIds: [SAVINGS] })

  it('sends only what actually moved', () => {
    expect(pendingUpdates({ c1: [SAVINGS, SUBSCRIPTION] }, [cat])).toEqual([
      { category_id: 'c1', tag_ids: [SAVINGS, SUBSCRIPTION] },
    ])
  })

  it('sends nothing for a row toggled on and back off', () => {
    const draft = toggleTag(toggleTag({}, cat, SUBSCRIPTION), cat, SUBSCRIPTION)
    expect(pendingUpdates(draft, [cat])).toEqual([])
  })

  it('counts an emptied set as a change — untagging is the point', () => {
    expect(pendingUpdates({ c1: [] }, [cat])).toEqual([{ category_id: 'c1', tag_ids: [] }])
  })

  it('ignores order', () => {
    const two = category({ tagIds: [SAVINGS, TRAVEL] })
    expect(pendingUpdates({ c1: [TRAVEL, SAVINGS] }, [two])).toEqual([])
  })

  it('drops a draft entry for a category that is no longer there', () => {
    expect(pendingUpdates({ gone: [SAVINGS] }, [cat])).toEqual([])
  })
})

describe('repairableTransferLegs', () => {
  it('excludes the legs that can never be paired', () => {
    // Saying "1,117 unmatched" when 200 are unmatchable by design is how a
    // number becomes a chore nobody finishes.
    expect(
      repairableTransferLegs(summary({ transfer_legs_unpaired: 1117, transfer_legs_in_splits: 200 }))
    ).toBe(917)
  })

  it('never reports a negative count', () => {
    expect(
      repairableTransferLegs(summary({ transfer_legs_unpaired: 3, transfer_legs_in_splits: 5 }))
    ).toBe(0)
  })
})

describe('initialFilter', () => {
  it('opens on what the import decided, when it decided something', () => {
    expect(
      initialFilter(
        summary({
          tagged_categories: [{ category_id: 'c1', system_key: 'savings', matched_on: 'Savings' }],
        })
      )
    ).toBe('decided')
  })

  it('opens on the proposals when there is no import to review', () => {
    // Otherwise the step opens empty for exactly the budgets that need it:
    // reopened from Settings, or built by hand, with no tags at all.
    expect(initialFilter(null)).toBe('suggested')
    expect(initialFilter(summary({ tagged_categories: [] }))).toBe('suggested')
  })
})
