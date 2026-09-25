import { describe, expect, it } from 'vitest'
import type { AIJob, AIJobDraft } from '../../api/aiJobs'
import { cardEndingNote, unresolvedCategoryNote } from './draftNotes'

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
