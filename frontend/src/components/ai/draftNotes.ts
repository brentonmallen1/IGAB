import type { AIJob, AIJobDraft } from '../../api/aiJobs'

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

/** What the receipt's card ending says about the account a scan sits in:
 *  - `elsewhere` — the card that paid is on file for a different account;
 *  - `unknown` — the receipt printed an ending nobody has on file, so the
 *    review offers to remember it for this account.
 *  Null when the receipt showed no card, the scan has no account yet, or the
 *  ending is this account's own. Which account owns an ending is served
 *  (`card_ending_account_id`); this only compares two served ids. */
export type CardEndingNote =
  | { kind: 'elsewhere'; last4: string; ownerId: string; hereId: string }
  | { kind: 'unknown'; last4: string; hereId: string }

export function cardEndingNote(job: AIJob): CardEndingNote | null {
  const last4 = job.result?.draft?.card_last4
  const hereId = job.transaction_account_id
  if (!last4 || !hereId) return null
  const ownerId = job.card_ending_account_id
  if (!ownerId) return { kind: 'unknown', last4, hereId }
  if (ownerId !== hereId) return { kind: 'elsewhere', last4, ownerId, hereId }
  return null
}
