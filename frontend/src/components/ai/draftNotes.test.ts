import { describe, expect, it } from 'vitest'
import type { AIJob, AIJobDraft } from '../../api/aiJobs'
import {
  aiSuggestedCategory,
  cardEndingNote,
  categoryForLabel,
  labelNamesCategory,
  unresolvedCategoryNote,
} from './draftNotes'
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
  const groupNames = new Map([
    ['household', 'Household'],
    ['holidays', 'Holidays'],
  ])
  const cats = [
    { id: 'gifts-home', name: 'Gifts', category_group_id: 'household' },
    { id: 'gifts-hols', name: 'Gifts', category_group_id: 'holidays' },
  ]

  it('finds a group-qualified split line', () => {
    // The editor's suggested split compared bare names, so a qualified line
    // like this one resolved to nothing and its picker was left empty.
    expect(categoryForLabel('Gifts (Holidays)', cats, groupNames)?.id).toBe('gifts-hols')
  })

  it('finds nothing for a category renamed since', () => {
    expect(categoryForLabel('Presents', cats, groupNames)).toBeUndefined()
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
