import { describe, it, expect } from 'vitest'
import {
  buildRows,
  filterRows,
  initialFilter,
  pendingUpdates,
  repairableTransferLegs,
  setTags,
  stepsFor,
  toggleTag,
  upcomingRows,
  type Draft,
  type ReviewCategory,
} from './importReview'
import type { YnabHeldOutFuture, YnabImportResult } from '../../../api/imports'
import type { ScheduledTransaction } from '../../../types'

const SAVINGS = 'tag-savings'
const SUBSCRIPTION = 'tag-subscription'
const TRAVEL = 'tag-travel' // the user's own, no system key
const ESSENTIAL = 'tag-essential'
const KEY_BY_ID = {
  [SAVINGS]: 'savings',
  [SUBSCRIPTION]: 'subscription',
  [ESSENTIAL]: 'essential',
}

function category(over: Partial<ReviewCategory> = {}): ReviewCategory {
  return {
    id: 'c1',
    name: 'Amazon Prime',
    groupName: 'Long Term Expenses',
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
    tracking_account_categories_stripped: 0,
    credit_card_payment_categories_stripped: 0,
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

  it('offers the upcoming step only when rows were held out', () => {
    expect(stepsFor(summary({ held_out_future: [] }))).toEqual(['summary', 'tags', 'accounts'])
    expect(stepsFor(summary({ held_out_future: [heldOut()] }))).toEqual([
      'summary',
      'upcoming',
      'tags',
      'accounts',
    ])
  })
})

function heldOut(over: Partial<YnabHeldOutFuture> = {}): YnabHeldOutFuture {
  return {
    scheduled_transaction_id: 's1',
    account_name: 'Checking',
    date: '2026-10-01',
    payee: 'Oakwood Property Mgmt',
    amount: '-1400.00',
    category_name: 'Rent',
    is_transfer: false,
    split_legs: [],
    ...over,
  }
}

describe('upcomingRows', () => {
  it('joins each held-out record to its live schedule', () => {
    const live = { id: 's1', frequency: 'once' } as ScheduledTransaction
    const [row] = upcomingRows(summary({ held_out_future: [heldOut()] }), [live])
    expect(row.schedule).toBe(live)
    expect(row.held.payee).toBe('Oakwood Property Mgmt')
  })

  it('marks a schedule that no longer exists rather than dropping the row', () => {
    // The summary records an event; a schedule entered or deleted since
    // still reads as "no longer upcoming" instead of vanishing.
    const [row] = upcomingRows(summary({ held_out_future: [heldOut()] }), [])
    expect(row.schedule).toBeNull()
  })

  it('treats a pre-feature summary as having nothing held out', () => {
    expect(upcomingRows(summary(), [])).toEqual([])
  })
})

describe('buildRows', () => {
  it('carries every tag, and names the system keys among them', () => {
    // Both halves matter: the row renders all of them, and only the system
    // keys can make a suggestion redundant.
    const cat = category({ tagIds: [SAVINGS, TRAVEL] })
    const [row] = buildRows([cat], [], [], KEY_BY_ID, {})
    expect(row.tagIds).toEqual([SAVINGS, TRAVEL])
    expect(row.heldKeys).toEqual(['savings'])
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

  it('moves a suggestion to accepted once the draft takes it up', () => {
    // Not dropped: ticking the box used to remove the offer, and with it the
    // row, before a second tag could be added. Not left open either, which
    // would read as though it had not applied.
    const cat = category()
    const suggestions = [
      {
        category_id: 'c1',
        system_key: 'subscription',
        matched_on: 'Amazon Prime',
        applied_on_import: false,
      },
    ]
    const before = buildRows([cat], suggestions, [], KEY_BY_ID, {})
    expect(before[0].suggestions).toHaveLength(1)

    const draft: Draft = { c1: [SUBSCRIPTION] }
    const after = buildRows([cat], suggestions, [], KEY_BY_ID, draft)
    expect(after[0].suggestions).toEqual([])
    expect(after[0].accepted).toEqual([{ systemKey: 'subscription', matchedOn: 'Amazon Prime' }])
    expect(after[0].heldKeys).toEqual(['subscription'])

    // Unticked again, it is an open offer once more.
    const undone = buildRows([cat], suggestions, [], KEY_BY_ID, { c1: [] })
    expect(undone[0].suggestions).toHaveLength(1)
    expect(undone[0].accepted).toEqual([])
  })
})

describe('filterRows', () => {
  const decided = category({ id: 'decided' })
  const proposed = category({ id: 'proposed' })
  const untouched = category({ id: 'untouched' })
  const rows = buildRows(
    [decided, proposed, untouched],
    [
      {
        category_id: 'proposed',
        system_key: 'essential',
        matched_on: 'Rent',
        applied_on_import: false,
      },
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

  it('keeps a proposed row under Suggested after its last offer is accepted', () => {
    // A real review: a suggestion was ticked with a second tag meant to
    // follow, and the row was gone before it could be added.
    const draft: Draft = { proposed: [ESSENTIAL] }
    const accepted = buildRows(
      [proposed, untouched],
      [
        {
          category_id: 'proposed',
          system_key: 'essential',
          matched_on: 'Rent',
          applied_on_import: false,
        },
      ],
      [],
      KEY_BY_ID,
      draft
    )
    expect(filterRows(accepted, 'suggested', draft).map((r) => r.category.id)).toEqual(['proposed'])
    // A row the user tagged by hand, never proposed, does not join the list.
    const handTagged = { untouched: [SAVINGS] }
    expect(
      filterRows(accepted, 'suggested', { ...draft, ...handTagged }).map((r) => r.category.id)
    ).toEqual(['proposed'])
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
      repairableTransferLegs(
        summary({ transfer_legs_unpaired: 1117, transfer_legs_in_splits: 200 })
      )
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

describe('setTags', () => {
  it('replaces the whole set, which is what a picker hands back', () => {
    const cat = category({ tagIds: [SAVINGS] })
    expect(setTags({}, cat, [TRAVEL, SUBSCRIPTION])).toEqual({ c1: [TRAVEL, SUBSCRIPTION] })
  })

  it('can clear a category outright', () => {
    const cat = category({ tagIds: [SAVINGS, TRAVEL] })
    expect(pendingUpdates(setTags({}, cat, []), [cat])).toEqual([
      { category_id: 'c1', tag_ids: [] },
    ])
  })

  it('reaches a category with no tags and no suggestions', () => {
    // The gap this closes: such a row had nothing to offer at all.
    const bare = category({ id: 'bare', name: 'Odds and Ends', tagIds: [] })
    const [row] = buildRows([bare], [], [], KEY_BY_ID, {})
    expect(row.tagIds).toEqual([])
    expect(row.suggestions).toEqual([])
    expect(pendingUpdates(setTags({}, bare, [TRAVEL, SAVINGS]), [bare])).toEqual([
      { category_id: 'bare', tag_ids: [TRAVEL, SAVINGS] },
    ])
  })
})

describe('the loan terms step', () => {
  // A YNAB export carries no account metadata at all, so every liability
  // arrives inert and an imported loan reads a month of interest below the
  // balance its source showed. Nothing else in the app knows an import just
  // happened, which is why the ask belongs in the review.
  it('is absent when every loan already has its terms', () => {
    expect(stepsFor(summary(), 0)).toEqual(['summary', 'tags', 'accounts'])
  })

  it('appears last when a loan is missing them', () => {
    expect(stepsFor(summary(), 1)).toEqual(['summary', 'tags', 'accounts', 'loans'])
  })

  it('appears for a budget with no stored summary too', () => {
    // Imported before IGAB kept a record: still has loans, still needs terms.
    expect(stepsFor(null, 2)).toEqual(['tags', 'accounts', 'loans'])
  })

  it('sits after upcoming when both are present', () => {
    const withHeldOut = summary({
      held_out_future: [{ scheduled_transaction_id: 's1' }] as never,
    })
    expect(stepsFor(withHeldOut, 1)).toEqual(['summary', 'upcoming', 'tags', 'accounts', 'loans'])
  })

  it('defaults to absent, so existing callers are unchanged', () => {
    expect(stepsFor(summary())).toEqual(['summary', 'tags', 'accounts'])
  })
})
