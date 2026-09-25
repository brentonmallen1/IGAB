import { describe, expect, it } from 'vitest'
import type { AIJobDraft } from '../../api/aiJobs'
import { unresolvedCategoryNote } from './draftNotes'

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
