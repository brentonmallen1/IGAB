import type { AIJobDraft } from '../../api/aiJobs'

/**
 * The sentence for a category the model named and the budget could not
 * resolve. Shown wherever the model's reason is, because the reason names
 * that category: beside an uncategorized row with no note, it read as the AI
 * having filed the receipt somewhere else (reported 2026-09-24).
 */
export function unresolvedCategoryNote(draft: AIJobDraft | undefined): string | null {
  const named = draft?.category_unresolved
  if (!named) return null
  return `Suggested “${named}”, which isn’t exactly one of your categories, so it’s left uncategorized.`
}
