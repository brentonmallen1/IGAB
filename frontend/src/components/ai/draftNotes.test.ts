import { describe, expect, it } from 'vitest'
import type { AIJob, AIJobDraft } from '../../api/aiJobs'
import {
  aiSuggestedCategory,
  cardEndingNote,
  categoryForLabel,
  checkStillOpen,
  checkedBoxes,
  draftCheckNotes,
  readNotes,
  labelNamesCategory,
  unresolvedCategoryNote,
} from './draftNotes'
import { buildCategoryLabels } from '../../utils/categoryLabels'
import labelCases from '../../../../shared/category_label_cases.json'

const draft = (over: Partial<AIJobDraft> = {}): AIJobDraft => ({
  payee: 'Hardware Store',
  amount: '-24.00',
  date: '2026-09-20',
  category: null,
  memo: null,
  confidence: 0.8,
  ...over,
})

describe('unresolvedCategoryNote', () => {
  it('names what the model suggested and says the row was left alone', () => {
    expect(unresolvedCategoryNote(draft({ category_unresolved: 'Garden' }))).toBe(
      'Suggested “Garden”, which isn’t exactly one of your categories, so it’s left uncategorized.'
    )
  })

  it('says nothing when the category resolved, or the model had no opinion', () => {
    expect(unresolvedCategoryNote(draft({ category: 'Garden – $150' }))).toBeNull()
    expect(unresolvedCategoryNote(draft({ category_unresolved: null }))).toBeNull()
    expect(unresolvedCategoryNote(draft())).toBeNull() // recorded before the field existed
    expect(unresolvedCategoryNote(undefined)).toBeNull()
  })
})

describe('cardEndingNote', () => {
  const job = (over: Partial<AIJob> = {}, last4: string | null = '4417'): AIJob =>
    ({
      result: { draft: { ...draft(), card_last4: last4 } },
      transaction_account_id: 'sapphire',
      card_ending_account_id: null,
      ...over,
    }) as AIJob

  it('offers to remember an ending nobody has on file', () => {
    expect(cardEndingNote(job())).toEqual({ kind: 'unknown', last4: '4417', hereId: 'sapphire' })
  })

  it("says so when the card that paid is another account's", () => {
    expect(cardEndingNote(job({ card_ending_account_id: 'harborstone' }))).toEqual({
      kind: 'elsewhere',
      last4: '4417',
      ownerId: 'harborstone',
      hereId: 'sapphire',
    })
  })

  it("is silent when the card is this account's own", () => {
    expect(cardEndingNote(job({ card_ending_account_id: 'sapphire' }))).toBeNull()
  })

  const switched = {
    from_account_id: 'harborstone',
    to_account_id: 'sapphire',
    card_last4: '4417',
  }

  it('records a scan the worker moved here by its card', () => {
    const moved = job({ card_ending_account_id: 'sapphire' })
    moved.result = { ...moved.result, account_switched: switched }
    expect(cardEndingNote(moved)).toEqual({
      kind: 'switched',
      last4: '4417',
      fromId: 'harborstone',
      hereId: 'sapphire',
    })
  })

  it('stops saying it was moved here once the row is moved back by hand', () => {
    const back = job({ transaction_account_id: 'harborstone', card_ending_account_id: 'sapphire' })
    back.result = { ...back.result, account_switched: switched }
    expect(cardEndingNote(back)?.kind).toBe('elsewhere')
  })

  it('is silent with no card on the receipt, or no account to compare with', () => {
    expect(cardEndingNote(job({}, null))).toBeNull()
    expect(cardEndingNote(job({ transaction_account_id: null }))).toBeNull()
    expect(cardEndingNote({ ...job(), result: null } as AIJob)).toBeNull()
  })
})

describe('labelNamesCategory: agreement with the server that writes the label', () => {
  for (const c of labelCases.cases) {
    it(`"${c.label}" (${c.note})`, () => {
      c.candidates.forEach(([name, group], i) => {
        expect(labelNamesCategory(c.label, { name, group })).toBe(i === c.index)
      })
    })
  }

  it('ignores case, as the server matcher does', () => {
    expect(labelNamesCategory('groceries', { name: 'Groceries', group: 'Everyday' })).toBe(true)
    expect(labelNamesCategory('GIFTS (HOLIDAYS)', { name: 'Gifts', group: 'Holidays' })).toBe(true)
  })

  it('reads only the bare name when the group is not known', () => {
    expect(labelNamesCategory('Gifts (Holidays)', { name: 'Gifts', group: null })).toBe(false)
    expect(labelNamesCategory('Gifts', { name: 'Gifts', group: null })).toBe(true)
  })
})

describe('categoryForLabel', () => {
  const cats = [
    { id: 'gifts-home', name: 'Gifts', category_group_id: 'household' },
    { id: 'gifts-hols', name: 'Gifts', category_group_id: 'holidays' },
  ]
  const labels = buildCategoryLabels(cats, [
    { id: 'household', name: 'Household' },
    { id: 'holidays', name: 'Holidays' },
  ])

  it('finds a group-qualified split line', () => {
    // The editor's suggested split compared bare names, so a qualified line
    // like this one resolved to nothing and its picker was left empty.
    expect(categoryForLabel('Gifts (Holidays)', cats, labels)?.id).toBe('gifts-hols')
  })

  it('finds nothing for a category renamed since', () => {
    expect(categoryForLabel('Presents', cats, labels)).toBeUndefined()
  })
})

describe('aiSuggestedCategory', () => {
  const filed = { name: 'Dining Out', group: 'Everyday' }

  it("names the model's pick when the row is filed elsewhere", () => {
    expect(aiSuggestedCategory(draft({ category: 'Groceries' }), filed)).toBe('Groceries')
  })

  it('says nothing when the row is where the model put it', () => {
    expect(aiSuggestedCategory(draft({ category: 'Dining Out' }), filed)).toBeNull()
  })

  it('reads a group-qualified pick as the same category', () => {
    expect(aiSuggestedCategory(draft({ category: 'Dining Out (Everyday)' }), filed)).toBeNull()
    expect(aiSuggestedCategory(draft({ category: 'Dining Out (Travel)' }), filed)).toBe(
      'Dining Out (Travel)'
    )
  })

  it('names the pick beside an uncategorized row', () => {
    expect(aiSuggestedCategory(draft({ category: 'Groceries' }), null)).toBe('Groceries')
  })

  it('is silent when the model named nothing, or nothing resolved', () => {
    // An unresolved pick has its own note (`unresolvedCategoryNote`).
    expect(aiSuggestedCategory(draft({ category_unresolved: 'Garden' }), null)).toBeNull()
    expect(aiSuggestedCategory(undefined, filed)).toBeNull()
  })
})

describe('draftCheckNotes', () => {
  const fmt = {
    formatDate: (iso: string) => `D(${iso})`,
    formatMoney: (n: number) => `$${n.toFixed(2)}`,
  }

  it('says a receipt too long to itemize kept only payee, total and date', () => {
    expect(draftCheckNotes(draft({ checks: ['items'] }), fmt)).toEqual([
      'The receipt was too long to read item by item, so only the payee, total and date were read — there’s no split to offer.',
    ])
  })

  it('names the date as it was read', () => {
    expect(draftCheckNotes(draft({ checks: ['date'], date_read: '2024-03-10' }), fmt)).toEqual([
      'The date read as D(2024-03-10), too far from today, so it’s set to today — check it.',
    ])
  })

  it('names the payment line a total disagrees with', () => {
    const notes = draftCheckNotes(
      draft({ amount: '-84.00', checks: ['amount'], tender_amount: '84.30' }),
      fmt
    )
    expect(notes).toEqual([
      'The total read as $84.00, but the payment line says $84.30 — check the amount.',
    ])
  })

  it('names what the items add up to', () => {
    const notes = draftCheckNotes(
      draft({ amount: '-84.30', checks: ['amount'], line_items_total: '96.10' }),
      fmt
    )
    expect(notes).toEqual(['The items add up to $96.10, not the total $84.30 — check the amount.'])
  })

  it('gives one note per disagreement, date first', () => {
    const notes = draftCheckNotes(
      draft({
        checks: ['date', 'amount'],
        date_read: '2024-03-10',
        tender_amount: '24.50',
        line_items_total: '30.00',
      }),
      fmt
    )
    expect(notes).toHaveLength(3)
    expect(notes[0]).toMatch(/^The date/)
  })

  it('says nothing for a read that passed, or predates the checks', () => {
    expect(draftCheckNotes(draft({ checks: [] }), fmt)).toEqual([])
    expect(draftCheckNotes(draft(), fmt)).toEqual([])
    expect(draftCheckNotes(undefined, fmt)).toEqual([])
  })
})

describe('checkStillOpen', () => {
  const checked = draft({ amount: '-24.00', date: '2026-09-20', checks: ['date', 'amount'] })

  it('is open while the field holds what the read put there', () => {
    const now = { date: '2026-09-20', cents: -2400 }
    expect(checkStillOpen(checked, 'date', now)).toBe(true)
    expect(checkStillOpen(checked, 'amount', now)).toBe(true)
  })

  it('closes once the field is changed — by a person or a bank row', () => {
    const now = { date: '2026-09-19', cents: -2430 }
    expect(checkStillOpen(checked, 'date', now)).toBe(false)
    expect(checkStillOpen(checked, 'amount', now)).toBe(false)
  })

  it('is never open for a field the read did not fail', () => {
    const now = { date: '2026-09-20', cents: -2400 }
    expect(checkStillOpen(draft({ checks: ['date'] }), 'amount', now)).toBe(false)
    expect(checkStillOpen(draft(), 'date', now)).toBe(false)
  })

  it('is not open while the amount is unreadable', () => {
    expect(checkStillOpen(checked, 'amount', { date: '2026-09-20', cents: null })).toBe(false)
  })
})

describe('checkedBoxes', () => {
  const checked = draft({ amount: '-24.00', date: '2026-09-20', checks: ['date', 'amount'] })

  it('outlines the box the amount sits in', () => {
    expect(checkedBoxes(checked, { date: '2026-09-20', cents: -2400 })).toEqual({
      date: true,
      outflow: true,
      inflow: false,
    })
    const refund = draft({ amount: '24.00', checks: ['amount'] })
    expect(checkedBoxes(refund, { date: '2026-09-20', cents: 2400 })).toEqual({
      date: false,
      outflow: false,
      inflow: true,
    })
  })

  it('outlines nothing once both are changed', () => {
    expect(checkedBoxes(checked, { date: '2026-09-19', cents: -2430 })).toEqual({
      date: false,
      outflow: false,
      inflow: false,
    })
  })
})

describe('readNotes', () => {
  const read = { attempt: 1, max_attempts: 3, thinking_setting: 'auto' as const, thinking: true }

  it('says nothing about an ordinary read', () => {
    expect(readNotes(read)).toEqual([])
    expect(readNotes(undefined)).toEqual([])
    expect(readNotes({ ...read, thinking: null })).toEqual([])
  })

  it('names a retry and the thinking fallback', () => {
    expect(readNotes({ ...read, attempt: 2, thinking: false, thinking_fallback: true })).toEqual([
      'Read on try 2 of 3',
      'Thinking turned off — it didn’t finish with it on',
    ])
  })

  it('names a Thinking setting that is not Auto', () => {
    expect(readNotes({ ...read, thinking_setting: 'off', thinking: false })).toEqual([
      'Thinking off (your setting)',
    ])
    expect(readNotes({ ...read, thinking_setting: 'on' })).toEqual(['Thinking on (your setting)'])
  })

  it('says nothing when Off was set but the model never thinks anyway', () => {
    expect(readNotes({ ...read, thinking_setting: 'off', thinking: null })).toEqual([])
  })
})
